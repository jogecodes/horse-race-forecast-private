# Public bookmaker browser capture pilot

The user authorized trying a public/manual pilot without an existing API or
account. A standard browser successfully rendered Sportium's public racing page
and one complete numeric-price market without login, credentials, CAPTCHA,
stealth configuration, certificate bypass, clicking odds or placing bets.
Existing Chromium/Playwright and local runtime libraries were reused; nothing
was installed or downloaded for this pilot. The browser was closed afterward.

## Observed prices

Sportium Bangor-on-Dee race 7, November 11, displayed scheduled time 16:35 in a
browser configured to Europe/Madrid. Captured at 13:22:01 UTC / 14:22:01 Madrid,
about 133 minutes before scheduled start.

| Cloth | Horse | Displayed current decimal odds |
|---|---|---:|
| 5 | Brookside La | 2.75 |
| 2 | Charisma Cat | 4.00 |
| 4 | Static | 4.00 |
| 3 | The Cistercian | 7.50 |
| 1 | Good To Be Alive | 8.50 |

The page advertised five participants, matching five captured named runners.
The selected tab was "Solo ganador o ganador y colocado". The current price
column was distinguished from "Cuotas anteriores". Two anonymous-favourite SP
selections were excluded from the runner list. No operator quote-update timestamp
was displayed; only our actual browser capture time is established.

This confirms public browser access to numerical prices more than an hour before
one UK race. It does not establish exact T-60 freshness, Spanish-race coverage,
executability, or an interesting/profitable bet. No Spanish-trained model
probabilities were applied to this UK race. No outcome was read or scored.

## Spanish pilot targets

The official La Zarzuela November 15 meeting page lists six races. Their planned
T-60 times in Europe/Madrid are 10:30, 11:05, 11:40, 12:15, 12:50 and 13:25.
These reflect the schedule captured on November 11, which must be checked again
before race day. Sportium's inspected Today/Tomorrow listings did not establish
coverage of that Sunday meeting.

The targets are a checklist, **not a scheduled background job**. No Spanish
prices were obtained and no candidate flags were produced. Next verify that the
Spanish races are actually listed, map the declared runners and capture complete
prices close enough to the fixed T-60 deadline. If the provider does not publish
a quote-update time, record that uncertainty and explicitly decide whether an
observation-time-only protocol is acceptable; do not fabricate a quote time to
pass the existing detector.

## Artifacts

`runs/public_capture_pilot_20261111/` contains:

- Full rendered HTML, text and screenshots for the public landing page, UK race,
  tomorrow's listings and official Spanish meeting page.
- Capture/navigation receipts with actual UTC timestamps, source URLs and hashes.
- `structured_price_observation.json`: the five genuine displayed prices and
  explicit reasons this is not a qualifying Spanish T-60 detector input.
- `spanish_pilot_targets.json`: official schedule and six T-60 deadlines.
- `source/`: exact one-off browser capture scripts. They depend on an existing
  temporary browser runtime and are audit records, not a portable live collector.

No background browser, live scraper or betting process remains running.
