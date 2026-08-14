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

    try {
      const data = /\.TW$|\.TWO$|^\^TWII$|^\^TWOII$/i.test(sym)
        ? await fetchFromMIS(sym)
        : await fetchFromYahoo(sym);
      return jsonResponse(data, 200);
    } catch (err) {
      return jsonResponse({ error: String(err.message || err) }, 502);
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
  const j = await r.json();
  const m = (j.msgArray || [])[0];
  if (!m) throw new Error("MIS 沒有回傳這個代號的資料");

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
  const j = await r.json();
  const meta = j?.chart?.result?.[0]?.meta;
  if (!meta) throw new Error("Yahoo 沒有回傳這個代號的資料");

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
