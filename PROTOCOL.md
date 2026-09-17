# Neeble agent protocol

Neeble is a long-lived JSONL process. Start it once per browser session; send one request per planned browser action.

```json
{"goal":"Find the login page and open it","state":{"url":"https://site.test","elements":[]},"tools":[{"name":"goto","description":"Navigate to a URL"},{"name":"click_element","description":"Click a visible element"}]}
```

Each response is JSON. `legal_for_state` means only that the proposed action matches the supplied compact state. `verified` becomes true only when `NEEBLE_CDP_URL` is configured and the executor completes the action. The response includes the next compact state so the caller can immediately issue another request without a separate browser snapshot call.

```bash
export NEEBLE_CDP_URL=http://127.0.0.1:9222
neeble --weights /path/to/needle3.cact
```

The process keeps the Needle model and Playwright/CDP connection alive. It can navigate across multiple pages and tabs. Never send passwords, payment data, or arbitrary JavaScript to the routine policy layer; route those to the supervising model.
