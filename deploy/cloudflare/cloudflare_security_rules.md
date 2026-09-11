# Cloudflare Production Security & Rate Limiting Configuration

This document specifies the exact Cloudflare edge security rules for **Dawaiflow / ExpiryGuard** to terminate TLS, enforce HSTS, and block brute-force credential attacks on `/login` and `/token`.

---

## 1. WAF Rate Limiting Rule: Anti-Brute-Force on Authentication

### Rule Objective
Throttle and challenge repeated login attempts across `/login` and `/token` to prevent distributed credential stuffing and password guessing.

### Rule Parameters (Dashboard UI)
- **Rule Name**: `Dawaiflow Auth Anti-Brute-Force`
- **When incoming requests match**:
  ```text
  (http.request.uri.path eq "/login" or http.request.uri.path eq "/token") and http.request.method eq "POST"
  ```
- **Characteristics**: `IP Address`
- **Rate Limit Window**: `1 minute`
- **Request Threshold**: `5 requests`
- **Action**: `Managed Challenge` (or `Block` with 429 status)
- **Response Format**: `JSON`
  ```json
  {
    "detail": "Too many requests. Rate limit exceeded. Please wait 1 minute before trying again.",
    "error_code": "RATE_LIMIT_EXCEEDED"
  }
  ```
- **Mitigation Timeout**: `10 minutes`

---

## 2. Cloudflare SSL/TLS Encryption & HSTS Settings

Under **Cloudflare Dashboard > SSL/TLS**:

| Setting | Configuration | Rationale |
| :--- | :--- | :--- |
| **Encryption Mode** | **Full (Strict)** | Enforces end-to-end TLS between Cloudflare Edge and Nginx Origin with valid certs. |
| **Always Use HTTPS** | **ON** | Automatically redirects any HTTP requests to HTTPS (301). |
| **Minimum TLS Version** | **TLS 1.3** (or TLS 1.2) | Completely disables vulnerable TLS 1.0/1.1 and legacy ciphers. |
| **Opportunistic Encryption** | **ON** | Provides cryptographic confidentiality for older user agents. |
| **TLS 1.3 0-RTT** | **OFF** | **Critical**: Disabling 0-RTT prevents replay attacks on API POST/PUT requests. |
| **Automatic HTTPS Rewrites** | **ON** | Automatically upgrades mixed-content insecure resources. |

### HSTS Configuration (HTTP Strict Transport Security)
Under **SSL/TLS > Edge Certificates > HTTP Strict Transport Security (HSTS)**:
- **Enable HSTS (Strict-Transport-Security)**: `ON`
- **Max-Age Header**: `12 months (31536000)` or `24 months (63072000)`
- **Apply HSTS policy to subdomains**: `ON`
- **Preload**: `ON` (qualifies domain for global browser preload lists)
- **No-Sniff Header**: `ON`

---

## 3. Web Application Firewall (WAF) & Bot Protection

Under **Security > WAF**:
1. **Cloudflare Managed Ruleset**:
   - Status: `Enabled`
   - Action: `Block` for high-confidence threats (SQL Injection, XSS, Command Injection).
2. **Bot Fight Mode**:
   - Status: `Enabled` (Challenges automated bot scrapers and brute-force tools).
3. **Security Level**:
   - Setting: `Medium` (or `High` during active attack periods).

---

## 4. Terraform Configuration (Infrastructure as Code)

If deploying via Terraform, add this configuration block:

```hcl
# Cloudflare Zone Rate Limiting Rule for Dawaiflow Authentication
resource "cloudflare_ruleset" "dawaiflow_rate_limiting" {
  zone_id     = var.cloudflare_zone_id
  name        = "Dawaiflow Auth Rate Limiting"
  description = "Throttles /login and /token endpoints to 5 requests/minute per IP"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = "{\"detail\":\"Too many requests. Rate limit exceeded.\",\"error_code\":\"RATE_LIMIT_EXCEEDED\"}"
      }
    }
    ratelimit {
      characteristics     = ["cf.unique_visitor_id"]
      period              = 60
      requests_per_period = 5
      mitigation_timeout  = 600
    }
    expression  = "(http.request.uri.path in {\"/login\" \"/token\"}) and http.request.method == \"POST\""
    description = "Limit POST requests to /login and /token to 5 per minute"
    enabled     = true
  }
}

# Enforce Full Strict TLS and Minimum TLS 1.3
resource "cloudflare_zone_settings_override" "dawaiflow_settings" {
  zone_id = var.cloudflare_zone_id
  settings {
    ssl                      = "strict"
    always_use_https         = "on"
    min_tls_version          = "1.3"
    zero_rtt                 = "off"
    automatic_https_rewrites = "on"
    security_header {
      strict_transport_security {
        enabled            = true
        max_age            = 63072000
        include_subdomains = true
        preload            = true
        nosniff            = true
      }
    }
  }
}
```

---

## 5. Cloudflare API Deployment via cURL

To deploy the rate-limiting rule immediately using the Cloudflare REST API:

```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/rulesets/phases/http_ratelimit/entrypoint" \
     -H "Authorization: Bearer <CLOUDFLARE_API_TOKEN>" \
     -H "Content-Type: application/json" \
     --data '{
       "rules": [
         {
           "action": "block",
           "action_parameters": {
             "response": {
               "status_code": 429,
               "content_type": "application/json",
               "content": "{\"detail\":\"Too many requests. Rate limit exceeded.\",\"error_code\":\"RATE_LIMIT_EXCEEDED\"}"
             }
           },
           "ratelimit": {
             "characteristics": ["cf.unique_visitor_id"],
             "period": 60,
             "requests_per_period": 5,
             "mitigation_timeout": 600
           },
           "expression": "(http.request.uri.path in {\"/login\" \"/token\"}) and http.request.method == \"POST\"",
           "description": "Anti-Brute Force on /login and /token",
           "enabled": true
         }
       ]
     }'
```
