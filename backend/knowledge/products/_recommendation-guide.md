# Australian Life Insurance — Product Recommendation Master Guide

> **Purpose:** This file is the entry point for the LLM agent when generating product recommendations. Read this file first, then load the specific product comparison files listed below based on the client's needs.

---

## Product Knowledge Files

| File | Product Category | Use When |
|---|---|---|
| `life-cover-comparison.md` | Life / Death Cover | Client needs death benefit, terminal illness, or estate planning |
| `tpd-cover-comparison.md` | Total & Permanent Disability | Client needs disability lump sum, can't work permanently |
| `income-protection-comparison.md` | Income Protection (IP) | Client needs salary continuance during illness/injury |
| `trauma-cover-comparison.md` | Trauma / Critical Illness | Client wants lump sum on cancer, heart attack, stroke etc. |
| `super-fund-insurance.md` | Group / Super Fund Products | Client is asking about cover through their super fund |

---

## Step-by-Step Recommendation Framework

### Step 1 — Identify Client Needs

Ask or infer:
- What event are they protecting against? (death / disability / illness / income loss)
- Are they employed? Self-employed? What occupation class?
- Do they have existing cover (super fund, retail)?
- What is their budget / affordability concern?
- Do they have dependants, mortgage, debts?
- Are they inside or outside superannuation?

### Step 2 — Select Product Category

```
Client cannot work and it's permanent           → TPD Cover
Client cannot work and it's temporary           → Income Protection
Client diagnosed with serious illness           → Trauma Cover
Client death / terminal illness                 → Life Cover
Client in super fund with automatic cover       → Super Fund Group Insurance
Client needs multiple covers                    → Combine products (package discount available)
```

### Step 3 — Select Channel

| Channel | Best For | Trade-offs |
|---|---|---|
| **Retail (via adviser)** | High earners, complex needs, own-occupation TPD, trauma | Higher premium, full underwriting, richer definitions |
| **Group / Super fund** | Default cover, low cost, simple needs, under 25 opt-in | Simpler definitions, any-occupation TPD, limited trauma |
| **Direct (online)** | Simple life cover, quick coverage, young healthy clients | Stricter definitions, lower claim rates, sum limits |

### Step 4 — Select Provider

Load the relevant product file and compare providers using:
1. **TPD Definition** — own-occupation preferred; any-occupation cheaper
2. **Waiting / Benefit Period** — match to client's financial buffer
3. **Claims Acceptance Rate** — use historical data to rank providers
4. **Premium Level** — stepped vs level, age sensitivity
5. **Unique Features** — Vitality program (AIA), inflation indexing (Zurich), etc.
6. **Tax Efficiency** — IP premiums tax-deductible; life/TPD/trauma are not

### Step 5 — Generate Comparison Output

When presenting to the user, always include:
- A comparison table of the top 2–3 recommended products
- Key differences highlighted (definition, premium, wait period, claims rate)
- A clear recommendation with reasoning
- Tax implications
- Any exclusions or caveats relevant to the client's situation

---

## Quick Reference: Tax Treatment

| Cover Type | Premium Deductibility | Benefit Tax Treatment |
|---|---|---|
| Life Cover | NOT deductible | Tax-free to dependants; up to 15% tax to non-dependants from super |
| TPD | NOT deductible | Tax-free if paid outside super; taxed component if from super |
| Trauma | NOT deductible | Tax-free (lump sum, not income) |
| Income Protection | **DEDUCTIBLE** (outside super) | Taxable as income (insurer withholds tax) |
| Super Fund Premiums | Paid from concessional contributions (15% contributions tax) | Depends on benefit type and recipient |

---

## Quick Reference: Claims Acceptance Rates (APRA/ASIC Data)

| Cover Type | Adviser-Sold | Direct-Sold |
|---|---|---|
| Life / Death | ~97% | Lower |
| Income Protection | ~95% | Lower |
| TPD | ~84–87% | Lower |
| Trauma | ~84–87% | Lower |
| **Industry Average** | **~94–98%** | **Historically lower** |

> Adviser-sold (retail) policies consistently have higher claim acceptance rates than direct-sold policies. Use this when client is comparing channels.

---

## Quick Reference: Market Share (APRA Data)

| Insurer | Approx. Market Share | Primary Channel |
|---|---|---|
| TAL Life (Dai-ichi) | ~34–40% | Retail + Group |
| AIA Australia | ~18–20% | Retail + Group |
| Zurich / OnePath | ~14% | Retail |
| MLC / Nippon Life | ~10% | Group / Corporate |
| MetLife | Significant | Group / Super |
| Resolution Life (AMP) | Significant | Legacy retail |

---

## Common Exclusions Across All Products

- Suicide / self-harm within first 12–24 months of cover
- Extreme / dangerous sports (unless loading applied)
- War and declared military conflict
- Illegal drug use or criminal activity
- Non-disclosure or misrepresentation at application (voids claim)
- Pre-existing conditions (limited cover period in group/super)
- Inactive accounts in super (cover cancelled after 16 months)

---

## Regulatory Rules Summary

| Rule | Detail |
|---|---|
| PMIF / PYS (2019) | No automatic super cover for members under 25 or balance < $6,000 |
| Inactive accounts | Cover cancelled after 16 months no contributions (can opt-in) |
| Agreed-value IP | No longer sold to new customers; indemnity-value only |
| Trauma in super | No new trauma cover inside super since 2014 |
| TPD in super | Own-occupation permitted in retail; any-occupation is standard in super |
| AFCA | All insurance disputes can escalate to AFCA if insurer IDR fails |

---

## LLM Instruction: How to Present Recommendations

When generating a recommendation response:

1. State the **recommended product category** and why
2. Show a **comparison table** of top providers
3. Highlight the **single best option** with clear reasoning
4. Call out **tax benefits** (especially IP deductibility)
5. Flag any **exclusions or risks** relevant to the client
6. Note if the client should seek a **licensed financial adviser** for complex needs
7. If the client is in a super fund, always check group cover first before recommending retail
