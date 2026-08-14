// tw-stock-proxy — 即時股價 proxy（Cloudflare Worker）
//
// 用途：taiwan-market 網站前端瀏覽器直接呼叫證交所 MIS / Yahoo Finance
// 會被 CORS 擋掉（已用 Playwright 實測證實），這支 Worker 在伺服器端
// 幫忙代打這通 API，再用允許的 CORS header 把結果回給瀏覽器。
//
// 用法：GET /?sym=2330.TW  或 /?sym=^TWII  或 /?sym=AAPL
//
// 只允許 ALLOWED_ORIGIN 這個來源呼叫，不開放給任何網站當免費代理，
// 避免流量被其他人白嫖、共用的每日 10 萬次額度被吃光。

const ALLOWED_ORIGIN = "https://airinno.github.io";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const sym = url.searchParams.get("sym");

    if (!sym) {
      return jsonResponse({ error: "missing ?sym= parameter" }, 400);
    }

    // mode=history：當日走勢圖用的分鐘級資料（一律走 Yahoo，MIS 沒有這種歷史序列可查）
    const fetcher =
      url.searchParams.get("mode") === "history"
        ? fetchHistoryFromYahoo
        : /\.TW$|\.TWO$|^\^TWII$|^\^TWOII$/i.test(sym)
        ? fetchFromMIS
        : fetchFromYahoo;

    // 上游（MIS/Yahoo）偶爾會回傳暫時性錯誤（例如 Cloudflare 520），
    // 實測證實是暫時性、不是永久性擋 IP，重試一次即可解決，不用整支失敗。
    try {
      const data = await fetcher(sym);
      return jsonResponse(data, 200);
    } catch (firstErr) {
      try {
        const data = await fetcher(sym);
        return jsonResponse(data, 200);
      } catch (secondErr) {
        return jsonResponse({ error: String(secondErr.message || secondErr) }, 502);
      }
    }
  },
};

function toMisChannel(sym) {
  if (sym === "^TWII") return "tse_t00.tw";
  if (sym === "^TWOII") return "otc_o00.tw";
  if (/\.TWO$/i.test(sym)) return `otc_${sym.replace(/\.TWO$/i, "")}.tw`;
  return `tse_${sym.replace(/\.TW$/i, "")}.tw`;
}

function num(v) {
  const f = parseFloat(v);
  return Number.isFinite(f) && f > 0 ? f : null;
}

async function fetchFromMIS(sym) {
  const ch = toMisChannel(sym);
  const r = await fetch(
    `https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=${ch}&json=1&delay=0`,
    {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        Referer: "https://mis.twse.com.tw/stock/index.jsp",
      },
    }
  );
  let j;
  try {
    j = await r.json();
  } catch {
    throw new Error("MIS 暫時回應異常（非 JSON，可能上游短暫過載）");
  }
  const m = (j.msgArray || [])[0];
  if (!m) throw new Error("MIS 沒有回傳這個代號的資料，代號可能不存在");

  const prev = num(m.y);
  let price = num(m.z) || num(m.pz);
  if (price === null) {
    const bid = num((m.b || "").split("_")[0]);
    const ask = num((m.a || "").split("_")[0]);
    if (bid && ask) price = (bid + ask) / 2;
  }
  price = price || num(m.o) || prev;
  if (price === null || prev === null) throw new Error("MIS 資料不完整（可能盤前尚無成交）");

  return {
    sym,
    name: m.n || m.c || sym,
    price,
    prev,
    change: price - prev,
    pct: prev ? ((price - prev) / prev) * 100 : 0,
    ts: Math.floor(Number(m.tlong || 0) / 1000) || Math.floor(Date.now() / 1000),
    source: "twse-mis",
  };
}

async function fetchFromYahoo(sym) {
  const r = await fetch(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=1d`,
    { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" } }
  );
  let j;
  try {
    j = await r.json();
  } catch {
    throw new Error("Yahoo 暫時回應異常（非 JSON，可能上游短暫過載）");
  }
  const meta = j?.chart?.result?.[0]?.meta;
  if (!meta) throw new Error("Yahoo 沒有回傳這個代號的資料，代號可能不存在");

  const price = meta.regularMarketPrice;
  const prev = meta.chartPreviousClose ?? meta.previousClose;
  return {
    sym,
    name: meta.symbol || sym,
    price,
    prev,
    change: price - prev,
    pct: prev ? ((price - prev) / prev) * 100 : 0,
    ts: meta.regularMarketTime || Math.floor(Date.now() / 1000),
    source: "yahoo",
  };
}

// 當日走勢（分鐘級），給前端畫線圖用。一律走 Yahoo：
// MIS 只有「現在這一筆」的快照，沒有像 Yahoo 這樣的當天歷史序列可查。
// 注意：Yahoo 的台股資料本身有 15-20 分鐘延遲，走勢圖看的是趨勢形狀，
// 不是精確到分鐘的即時位置——跟上面即時報價（MIS，近乎零延遲）是不同用途。
async function fetchHistoryFromYahoo(sym) {
  const r = await fetch(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=5m&range=1d`,
    { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" } }
  );
  let j;
  try {
    j = await r.json();
  } catch {
    throw new Error("Yahoo 暫時回應異常（非 JSON，可能上游短暫過載）");
  }
  const result = j?.chart?.result?.[0];
  if (!result) throw new Error("Yahoo 沒有回傳這個代號的歷史資料，代號可能不存在");

  const timestamps = result.timestamp || [];
  const closes = result.indicators?.quote?.[0]?.close || [];
  const points = [];
  for (let i = 0; i < timestamps.length; i++) {
    if (closes[i] != null) points.push({ ts: timestamps[i], price: closes[i] });
  }
  if (!points.length) throw new Error("今天目前沒有可畫的走勢資料（可能尚未開盤）");

  return { sym, points, source: "yahoo-intraday" };
}

function jsonResponse(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      // Cloudflare edge cache 15 秒：同一標的短時間內多人瀏覽只打一次上游 API
      "Cache-Control": "public, max-age=15",
    },
  });
}
