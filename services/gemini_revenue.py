import os
import re

OMNI_SYSTEM_PROMPT = """You are OMNI-REVENUE ARCHITECT — a Senior Revenue Management expert with 15+ years at Marriott, Four Seasons, Airbnb and large STR portfolios. You think like a CFO, act like a Revenue Manager, analyze like a Data Scientist.

YOUR JOB: Generate a complete, detailed, actionable revenue strategy for the property described below.

EXPERT RULES:
1. When data is provided → use it exactly as given for calculations
2. When data is missing → apply your deep expert knowledge for this property type, location and market. You MUST generate concrete recommendations regardless of missing data.
3. ALWAYS generate specific numbers in the property's currency. Never write vague advice.
4. Base all pricing on the floor rate and any rates provided. Calculate all derived rates from those.
5. Your recommendations must be specific enough to execute tomorrow morning.

DECISION FRAMEWORK:
- If channel mix shows OTA > 60%: prioritize direct channel and reduce OTA dependency
- If occupancy < 60%: focus on visibility, pricing competitiveness, and channel diversification
- If occupancy > 80%: raise rates aggressively, apply MinLOS, close cheapest plans
- Always: Direct rate = cheapest for guest, most profitable for hotel (0% commission)
- Always: Luxury never discounts, adds value. Budget competes on visibility + reviews.

OUTPUT: You MUST produce all 10 sections below. Each section must have specific numbers, tables with actual amounts, and concrete action steps. If a metric wasn't provided, calculate it from what was given or state your expert assumption clearly.

## 1. Property DNA Profile
[3-4 sentences: market position, competitive advantage, pricing power, key risks and opportunities]

## 2. Diagnosis & Key Issues Detected
[Bullet list of specific issues found with metric and financial impact in property currency]
- Issue: [description] → Impact: [amount or %]

## 3. Demand Forecast (next 7 / 14 / 30 days)
| Period | Expected Demand | Confidence | Recommended ADR | Key Driver |
|--------|----------------|------------|-----------------|------------|
| Next 7 days | High/Med/Low | X% | [amount] | [event/season] |
| Next 14 days | ... | ... | [amount] | ... |
| Next 30 days | ... | ... | [amount] | ... |

## 4. Dynamic Pricing Matrix
Base rate: [floor or ADR provided]
| Occupancy | Lead > 30d | Lead 15-30d | Lead < 7d |
|-----------|-----------|-------------|-----------|
| 0-30% (Low) | [amount] | [amount] | [amount Flash] |
| 31-60% (Normal) | [amount] | [amount] | [amount] |
| 61-90% (High) | [amount] | [amount] | [amount Rack] |
| 91-100% (Compression) | [amount Premium] | [amount Premium] | CTD Active |

## 5. Rate Plan Architecture
| Plan | Amount | Conditions | Channel |
|------|--------|------------|---------|
| BAR (Best Available) | [amount] | Flexible | All OTAs |
| Non-Refundable | [amount -15%] | No cancellation | Booking/Expedia |
| Early Bird | [amount -10%] | 30+ days advance | All |
| Direct Rate ★ | [amount -8%] | 0% commission | Website/WhatsApp |
| Value Package | [amount] | Includes [extras] | Direct |
[Add per room type if multiple types]

## 6. Inventory Restrictions
- MinLOS [X nights]: [specific dates/conditions and why]
- CTA (Closed to Arrival): [dates]
- CTD (Closed to Departure): [when to activate]
- Overbooking %: [% with rationale]

## 7. Channel Strategy & Distribution — OTAs + Direct + Paid Media
Current mix: [from data or assumed]
Target mix in 6 months: X% Direct / X% Booking / X% Other

**Booking.com — Activate:**
- [Specific promotion with discount % and expected ranking impact]

**Expedia — Activate:**
- [Specific promotion]

**Google Hotel Ads:**
- [Setup steps and why: CPE ~8% vs Booking 15%]
- Net gain per booking vs Booking: [calculated amount in currency]

**Direct Channel:**
- [Specific perks to offer: upgrades, late checkout, etc.]
- [Email retargeting: estimated guests × conversion % = revenue]

**Paid Media Channels:**
- [Platform: Meta/Google/TikTok — targeting, budget, expected ROAS]

**Commission Impact Analysis:**
- Booking: guest pays [X] → hotel nets [X] after -[X]% = [net amount]
- Direct: guest pays [X] → hotel nets [X] (0% commission) = saves [diff] per booking
- Monthly NRevPAR gain from 35% direct mix: [calculated amount]

## 8. Revenue Opportunities (Upsell / Cross-sell / Ancillary)
| Opportunity | Price | Est. Sales/Month | Monthly Revenue |
|-------------|-------|-----------------|-----------------|
| [Item 1] | [amount] | [units] | [total] |
| [Item 2] | [amount] | [units] | [total] |
Total ancillary potential: [sum] [currency]/month

## 9. Action Plan

### Immediate (Today)
1. [Platform] → [Exact action] → Expected impact: [amount in currency]
2. [Platform] → [Exact action] → Expected impact: [amount in currency]
3. [Platform] → [Exact action] → Expected impact: [amount in currency]

### Next 7 Days
1. [Action with tool and expected impact]
2. [Action with tool and expected impact]

### Next 30 Days
1. [Action with tool and expected impact]
2. [Action with tool and expected impact]

## 10. KPIs to Monitor
| KPI | Current | Target | Alert Threshold |
|-----|---------|--------|-----------------|
| NRevPAR | [current] | [target] | Below [X] |
| ADR | [current] | [target] | Below [X] |
| Occupancy % | [current] | [target %] | Below [X]% |
| Direct Booking % | [current]% | [target]% | Below [X]% |
| Monthly Revenue | [current] | [target] | Below [X] |
| Pickup pace | — | [X bookings/day] | Below [Y]/day |"""

SECTION_MAP = {
    '1': 'dna', '2': 'diagnosis', '3': 'forecast',
    '4': 'matrix', '5': 'rates', '6': 'restrictions',
    '7': 'channels', '8': 'upsell', '9': 'action', '10': 'kpis'
}


def build_property_prompt(data: dict) -> str:
    prop = data.get('property', {})
    rooms = data.get('room_types', [])
    compset = data.get('compset', [])
    perf = data.get('performance', {}) or {}
    market = data.get('market', {}) or {}
    currency = prop.get('currency', 'COP')

    def fmt(v):
        if v is None or v == '' or v == 0:
            return None
        try:
            return f"{currency} {float(v):,.0f}"
        except (TypeError, ValueError):
            return str(v) if v else None

    def line(label, value, suffix=''):
        v = fmt(value) if isinstance(value, (int, float)) else (str(value) if value else None)
        if v:
            return f"- {label}: {v}{suffix}"
        return None

    parts = ["=== PROPERTY DATA ===\n"]

    # PMS data first — highest priority
    pms = (prop.get('pms_raw_data') or
           data.get('pms_raw_data') or '').strip()
    if pms:
        parts.append("=== PMS/OTA REPORT DATA (PRIMARY SOURCE — USE THESE NUMBERS) ===")
        parts.append(pms[:4000])
        parts.append("=== END PMS DATA ===\n")

    # Property identity
    parts.append("Property Profile:")
    for lbl, val in [
        ("Name", prop.get('name')),
        ("Location", prop.get('city')),
        ("Type", prop.get('property_type')),
        ("Positioning", prop.get('positioning')),
        ("Stars", prop.get('star_rating')),
        ("Brand strength", prop.get('brand_strength')),
        ("Total rooms/units", prop.get('total_rooms')),
        ("Owner minimum price floor", fmt(prop.get('price_floor'))),
        ("Currency", currency),
        ("USPs", prop.get('usp_text')),
        ("Amenities", prop.get('amenities')),
        ("Extras/Add-ons", prop.get('extras')),
    ]:
        if val:
            parts.append(f"- {lbl}: {val}")

    # Room types
    if rooms:
        parts.append("\nRoom Types:")
        for rt in rooms:
            r = fmt(rt.get('derived_rate') or prop.get('price_floor'))
            bkf = rt.get('breakfast_per_pax', 0) or 0
            occ = rt.get('occupancy_pct', 55)
            parts.append(
                f"- {rt['name']}: {rt['units']} units | "
                f"max {rt.get('pax_max', 2)} pax | "
                f"rate {r}" +
                (f" + breakfast {fmt(bkf)}/pax" if bkf else "") +
                f" | occupancy {occ}%"
            )

    # Performance metrics — only include what was actually provided
    perf_lines = []
    metric_map = [
        ('occupancy_pct',         '% Occupancy',              False),
        ('adr',                   'ADR (Average Daily Rate)',  True),
        ('revpar',                'RevPAR',                    True),
        ('total_monthly_revenue', 'Total Monthly Revenue',     True),
        ('total_nights_available','Total Nights Available/Month', False),
        ('nights_sold',           'Nights Sold/Month',         False),
        ('booking_window_days',   'Avg Booking Window (days)', False),
        ('avg_los',               'Avg LOS (nights)',          False),
        ('cancellation_pct',      'Cancellation Rate %',       False),
        ('city_avg_occ_pct',      'City Average Occupancy %',  False),
        ('guest_segment',         'Primary Guest Segment',     False),
        ('feeder_markets',        'Top Feeder Markets',        False),
    ]
    for key, label, is_money in metric_map:
        v = perf.get(key)
        if v is not None and v != '' and v != 0:
            display = fmt(v) if is_money else (f"{v}%" if 'pct' in key else str(v))
            perf_lines.append(f"- {label}: {display}")

    # Channel mix
    ch_parts = []
    for k, lbl in [('channel_direct_pct','Direct'),('channel_booking_pct','Booking.com'),
                   ('channel_expedia_pct','Expedia'),('channel_airbnb_pct','Airbnb'),
                   ('channel_corp_pct','Corporate')]:
        v = perf.get(k, 0) or 0
        if v:
            ch_parts.append(f"{lbl} {v}%")
    if ch_parts:
        perf_lines.append(f"- Channel mix: {' / '.join(ch_parts)}")

    if perf_lines:
        parts.append("\nCurrent Performance (Last 30 Days):")
        parts += perf_lines
    else:
        parts.append("\nCurrent Performance: Not provided — apply expert knowledge for this property type.")

    # Market
    mkt_lines = []
    if market.get('market_avg_rate'):
        mkt_lines.append(f"- Market average rate: {fmt(market['market_avg_rate'])}")
    if market.get('demand_level'):
        mkt_lines.append(f"- Current demand: {market['demand_level']}")
    if market.get('seasonality'):
        mkt_lines.append(f"- Seasonality: {market['seasonality']}")
    if market.get('upcoming_events'):
        mkt_lines.append(f"- Upcoming events: {market['upcoming_events']}")
    if market.get('demand_drivers'):
        mkt_lines.append(f"- Demand drivers: {market['demand_drivers']}")
    if mkt_lines:
        parts.append("\nMarket Context:")
        parts += mkt_lines

    # CompSet
    if compset:
        parts.append("\nCompetitive Set:")
        for c in compset:
            if c.get('name'):
                r = fmt(c.get('avg_rate'))
                parts.append(
                    f"- {c['name']}: rate {r or 'unknown'} | position vs us: {c.get('position','similar')}"
                )

    parts += [
        "",
        f"=== GENERATE COMPLETE 10-SECTION OMNI-REVENUE ANALYSIS ===",
        f"Currency: {currency}",
        "Generate specific numbers for EVERY section. Be the expert. Recommend boldly.",
        "If a metric was not provided, calculate it from available data or state your expert assumption.",
    ]

    return "\n".join(parts)


def parse_sections(raw: str) -> dict:
    """Robust section parser — handles various markdown formats from Groq."""
    sections = {}
    if not raw:
        return sections

    # Try multiple patterns to find section boundaries
    # Pattern 1: ## 1. Title or ## 1. Title (most common)
    pattern = re.compile(
        r'(?:^|\n)(##\s+\*{0,2}(\d+)[\.\)]\*{0,2}\s+.+?)(?=\n##\s+\*{0,2}\d+[\.\)]|\Z)',
        re.DOTALL | re.MULTILINE
    )
    matches = list(pattern.finditer(raw))

    if not matches:
        # Fallback: split by numbered sections more liberally
        pattern2 = re.compile(
            r'(?:^|\n)#+\s*\*{0,2}(\d+)[\.\)]\*{0,2}',
            re.MULTILINE
        )
        boundaries = [(m.start(), m.group(1)) for m in pattern2.finditer(raw)]
        for i, (start, num) in enumerate(boundaries):
            end = boundaries[i+1][0] if i+1 < len(boundaries) else len(raw)
            key = SECTION_MAP.get(num)
            if key:
                sections[key] = raw[start:end].strip()
        return sections

    for match in matches:
        content = match.group(1).strip()
        num = match.group(2)
        key = SECTION_MAP.get(num)
        if key:
            sections[key] = content

    return sections


def generate_omni_analysis(data: dict) -> dict:
    from groq import Groq

    api_key = os.environ.get('GROQ_API_KEY', '')
    if not api_key:
        raise ValueError("GROQ_API_KEY no está configurado. Agrégalo en Railway → Variables.")

    client = Groq(api_key=api_key)
    prompt = build_property_prompt(data)

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {'role': 'system', 'content': OMNI_SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt}
        ],
        temperature=0.5,
        max_tokens=8000,
    )

    raw = response.choices[0].message.content or ''
    sections = parse_sections(raw)

    # If parser found nothing, store entire response in dna section
    if not sections and raw.strip():
        sections = {'dna': raw}

    return {'raw': raw, 'sections': sections}
