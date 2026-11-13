# Regulatory map

How each rule relates to RBI guidance. The wording is "supports" or "aligned with", never "compliant". This is a design mapping done by the team, not legal advice, and it has not been reviewed by a bank or a lawyer. Check each instrument's text before quoting it.

**Strength labels**
- **Mandated:** the instrument requires a control of this kind.
- **Permitted:** the instrument allows the control (for example as a risk-based factor).
- **Industry / Best practice:** common practice or RBIH guidance, not an RBI requirement.
- **Unverified:** we could not confirm it. Do not cite.

| Rule | Plain title | Treatment | Basis (strength) |
|---|---|---|---|
| R1 | Much larger than usual | Hold + step-up authentication | RBI Authentication Mechanisms Directions 2025 (Permitted); RBI Digital Payment Security Controls 2021 (Mandated) |
| R2 | New payee, big amount | Hold + confirmation or callback | Bank cooling-off practice (Industry) |
| R3 | Too many payments in an hour | Block | RBI Digital Payment Security Controls 2021 (Mandated) |
| R4 | New phone, money moving | Hold + step-up authentication | RBI Authentication Directions 2025 (Permitted) |
| R5 | Paying many different people quickly | Block | RBIH MuleHunter.AI patterns (Best practice); RBI Fraud Risk Management Directions 2024 (Mandated) |
| R6 | Large payment at night | Hold + step-up authentication | RBI Authentication Directions 2025 (Permitted) |
| R7 | Money passes straight through | Hold + review | RBIH MuleHunter.AI mule patterns (Best practice); RBI Fraud Risk Management Directions 2024 (Mandated) |

## Process controls (not rules)
| Control in FraudArena | Idea it supports |
|---|---|
| A second person must approve every rule change | Maker-checker governance expected under fraud-risk management directions |
| Hash-chained, signed ledger of every change | Auditable record of control changes |
| Customer-facing message for every hold or block | Customer communication and the 2017 customer-liability circular's emphasis on prompt notice |

## Deliberately not claimed
- A "hold on new payees above 2,000 rupees" rule: marked **Unverified**, not cited.
- Compliance with any directive. The rules are aligned with the guidance; a bank decides what it must implement.

## What the data adds
Thresholds come from the RBIH NFPC Phase-2 data (see `DATA_CARD.md`), so each rule's friction and mule coverage is measured, not guessed. Two signals cannot be measured from that data: device change and new-payee age.
