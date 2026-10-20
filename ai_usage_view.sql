-- Run in the Supabase SQL editor. Additive; nothing else reads these.

CREATE TABLE IF NOT EXISTS ai_usage_log (
    id               SERIAL PRIMARY KEY,
    event_id         VARCHAR(40) NOT NULL UNIQUE,
    created_at       TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    shop_id          INTEGER,
    feature          VARCHAR(32) NOT NULL,
    model            VARCHAR(64),
    source           VARCHAR(8) NOT NULL DEFAULT 'backend',
    outcome          VARCHAR(16) NOT NULL,
    call_no          INTEGER,
    prompt_tokens    INTEGER,
    output_tokens    INTEGER,
    thought_tokens   INTEGER,
    total_tokens     INTEGER,
    cost_inr         DOUBLE PRECISION,
    cost_usd         DOUBLE PRECISION,
    price_in_per_m   DOUBLE PRECISION,
    price_out_per_m  DOUBLE PRECISION,
    usd_inr          DOUBLE PRECISION,
    bill_id          VARCHAR(40),
    rows             INTEGER,
    pages            INTEGER,
    strips           INTEGER,
    latency_ms       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_shop_time    ON ai_usage_log (shop_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_feature_time ON ai_usage_log (feature, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_bill         ON ai_usage_log (bill_id);

-- Per pharmacy per day: calls, tokens (thinking counted as output), rupees
CREATE OR REPLACE VIEW ai_usage_daily AS
SELECT shop_id,
       date_trunc('day', created_at)::date                        AS day,
       count(*) FILTER (WHERE outcome <> 'cache_hit')             AS calls,
       count(*) FILTER (WHERE outcome = 'cache_hit')              AS cache_hits,
       coalesce(sum(prompt_tokens), 0)                            AS input_tokens,
       coalesce(sum(coalesce(output_tokens,0) + coalesce(thought_tokens,0)), 0) AS output_tokens,
       round(coalesce(sum(cost_inr), 0)::numeric, 4)              AS cost_inr
FROM ai_usage_log
GROUP BY shop_id, date_trunc('day', created_at);

-- Per feature: average and p95 rupees per call (calls with usage numbers only, cache hits excluded)
CREATE OR REPLACE VIEW ai_usage_feature_stats AS
SELECT feature,
       count(*)                                                   AS calls,
       round(avg(cost_inr)::numeric, 4)                           AS avg_inr_per_call,
       round((percentile_cont(0.95) WITHIN GROUP (ORDER BY cost_inr))::numeric, 4) AS p95_inr_per_call
FROM ai_usage_log
WHERE outcome <> 'cache_hit' AND cost_inr IS NOT NULL
GROUP BY feature;

-- Average rupees per invoice bill (both readings of one bill summed)
CREATE OR REPLACE VIEW ai_usage_invoice_bill_cost AS
SELECT round(avg(bill_cost)::numeric, 4) AS avg_inr_per_bill, count(*) AS bills
FROM (SELECT bill_id, sum(cost_inr) AS bill_cost
      FROM ai_usage_log
      WHERE feature IN ('invoice_read','invoice_second_pass') AND outcome <> 'cache_hit'
        AND cost_inr IS NOT NULL AND bill_id IS NOT NULL
      GROUP BY bill_id) b;

-- Total rupees per pharmacy per month
CREATE OR REPLACE VIEW ai_usage_monthly AS
SELECT shop_id, to_char(created_at, 'YYYY-MM') AS month, count(*) AS calls,
       round(coalesce(sum(cost_inr),0)::numeric, 4) AS cost_inr
FROM ai_usage_log WHERE outcome <> 'cache_hit'
GROUP BY shop_id, to_char(created_at, 'YYYY-MM');
