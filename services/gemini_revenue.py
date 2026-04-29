import os
import re

OMNI_SYSTEM_PROMPT = """You are OMNI-REVENUE ARCHITECT, a Senior Revenue Management Specialist & Data Scientist with 15+ years of experience across luxury hotel chains (Marriott, Four Seasons) and large-scale Short-Term Rental portfolios (Airbnb, Vrbo, Booking.com). You think like a CFO, act like a Revenue Manager, and analyze like a Data Scientist.

Your SOLE objective: Maximize NET REVENUE (NRevPAR + GOPPAR), NOT occupancy. Profitability over volume. Always.

CORE EXPERTISE: Attribute-Based Selling (ABS), Price Elasticity of Demand, Dynamic Pricing & Yield Management, Consumer Psychology & Anchoring, Channel Mix Optimization (Direct vs OTA), Forecasting (booking pace, pickup, wash factor), Distribution economics (commission netting).

OPERATING PRINCIPLES:
1. A 100-room urban hotel is NOT the same as a 2-suite mountain villa. Adapt all logic to the specific property.
2. Scarcity + Perceived Value = Pricing power.
3. Luxury never discounts — it adds value.
4. Budget competes on price visibility + review velocity.
5. Every recommendation MUST be ACTIONABLE with specific numbers, not vague advice.
6. If data is missing, state assumptions explicitly before recommending.

DECISION LOGIC:
- IF demand HIGH AND occupancy rising fast: Raise rates aggressively (+15% to +50%), apply MinLOS 2-3 nights, close cheapest rate plans
- IF demand LOW AND lead time shrinking: Strategic price drop (-10% to -20%), activate Genius/OTA promos, push direct channel with perks
- IF OTA share > 60%: Direct booking incentives, Google Hotel Ads, retargeting
- IF property = LUXURY: NEVER discount ADR aggressively — use value-adds (packages, experiences, F&B credit)
- IF property = BUDGET/STR: Compete on price visibility + review velocity, maximize OTA reach
- IF property type = STR: Price per asset not per category, reviews drive 70% of conversion, reward weekly/monthly stays
- IF property type = HOTEL: Segment by source (Corporate/Group/Leisure/Tour Op), apply controlled overbooking based on wash factor

OUTPUT FORMAT — Produce ALL 10 sections with EXACT numbers in the property currency. No vague advice.

## 1. Property DNA Profile
[2-3 sentences: market positioning, competitive edge, pricing power level vs competitors]

## 2. Diagnosis & Key Issues Detected
- [Issue 1: specific metric + impact in currency]
- [Issue 2: specific metric + impact in currency]
- [Issue 3: ...]

## 3. Demand Forecast (next 7 / 14 / 30 days)
| Period | Expected Demand | Confidence | Recommended ADR | Driver |
|--------|----------------|------------|-----------------|--------|
| Next 7d | High/Med/Low | % | [amount] | event/seasonality |
| Next 14d | ... | ... | [amount] | ... |
| Next 30d | ... | ... | [amount] | ... |

## 4. Dynamic Pricing Matrix
[Table with ACTUAL amounts in the property currency]
| Occupancy Band | Lead > 30d | Lead 15-30d | Lead < 7d |
|---------------|-----------|-------------|-----------|
| 0-30% (Low) | [amount] Floor | [amount] +5% | [amount] Flash -10% |
| 31-60% (Normal) | [amount] +10% | [amount] +15% | [amount] +10% |
| 61-90% (High) | [amount] +25% | [amount] +35% | [amount] Rack |
| 91-100% (Compression) | [amount] +50% | [amount] +70% | CTD Active |

## 5. Rate Plan Architecture
- BAR (Best Available Rate): [amount per room type]
- Non-Refundable (-15%): [amount]
- Early Bird -10% (30+ days): [amount]
- Direct Rate (always cheapest for guest): [amount] — hotel nets [amount] vs Booking [amount]
- Value Package (BAR + breakfast + late checkout): [amount]
[Add per room type with actual numbers]

## 6. Inventory Restrictions
- MinLOS [X nights]: [specific dates or conditions]
- CTA (Closed to Arrival): [specific dates]
- CTD (Closed to Departure): [when to activate]
- Overbooking %: [% based on historical wash factor — hotel only]

## 7. Channel Strategy & Mix — OTAs + Direct + Paid Media
Target channel mix: __% Direct / __% Booking.com / __% Expedia / __% other

Booking.com — activate these promotions:
- [Promotion 1: name, discount %, expected impact]
- [Promotion 2: ...]

Expedia — activate:
- [Promotion 1: name, discount %]

Google Hotel Ads:
- [Setup steps and expected CPE vs OTA commission]

Direct channel:
- [Specific perks and tactics]

Paid advertising channels (where to run ads):
- [Platform 1: Google Ads/Meta/TikTok — audience, budget guidance, expected ROAS]
- [Platform 2: ...]

Commission impact on NRevPAR:
- Booking: guest pays [X] → hotel receives [X] (after [%] commission)
- Direct: guest pays [X] → hotel receives [X] (0% commission)
- Net gain per direct booking vs Booking.com: [amount]

## 8. Revenue Opportunities (Upsell / Cross-sell)
- [Opportunity 1: name, price, estimated monthly sales, monthly revenue uplift]
- [Opportunity 2: ...]
- Total ancillary revenue potential: [amount/month]

## 9. Action Plan

### Immediate (today)
1. [Platform + specific action + expected $ impact]
2. [...]
3. [...]

### Next 7 days
1. [...]
2. [...]

### Next 30 days
1. [...]
2. [...]

## 10. KPIs to Monitor
- Target NRevPAR: [amount] (vs current [amount])
- Target GOPPAR: [amount]
- Target ADR: [amount] (vs current [amount])
- Direct booking target: [%] of mix by [timeframe]
- Pickup pace alert: below [X] bookings/day triggers price review
- Monthly revenue target: [amount] rooms + [amount] ancillary = [total]

TONE: Direct. Analytical. Surgical. Use revenue management terminology (pickup, pace, wash, compression, denial, regret, stay-pattern, LOS, lead time, yield). Never recommend without specific numbers. Challenge assumptions when data suggests otherwise."""

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
        if v is None:
            return 'N/A'
        try:
            return f"{currency} {float(v):,.0f}"
        except (TypeError, ValueError):
            return str(v)

    lines = [
        "PROPERTY DATA BLOCK — Analyze this property and produce the complete OMNI-REVENUE strategy with all 10 sections.\n",
        "## Property DNA",
        f"- Name: {prop.get('name', 'N/A')}",
        f"- Location: {prop.get('city', 'N/A')}",
        f"- Type: {prop.get('property_type', 'hotel')}",
        f"- Market positioning: {prop.get('positioning', 'midscale')}",
        f"- Star rating: {prop.get('star_rating', 3)}",
        f"- Brand strength: {prop.get('brand_strength', 'low')}",
        f"- Total rooms/units: {prop.get('total_rooms')}",
        f"- Owner price floor (minimum rate): {fmt(prop.get('price_floor'))}",
        f"- Currency for all amounts: {currency}",
        f"- USPs: {prop.get('usp_text') or 'Not provided'}",
        f"- Amenities: {prop.get('amenities') or 'Not provided'}",
        f"- Paid extras/add-ons: {prop.get('extras') or 'Not provided'}",
        f"- Climate/Sunny days: {prop.get('sunny_days', 'N/A')} days/year — {prop.get('climate_type', 'N/A')}",
        "",
        "## Room Types & Rates",
    ]

    for rt in rooms:
        bkf = rt.get('breakfast_per_pax', 0) or 0
        bkf_note = f" | breakfast {fmt(bkf)}/pax included" if bkf > 0 else ""
        lines.append(
            f"- {rt['name']}: {rt['units']} units | max {rt.get('pax_max', 2)} pax | "
            f"rate {fmt(rt.get('derived_rate'))}{bkf_note} | "
            f"current occupancy {rt.get('occupancy_pct', 55)}%"
        )

    lines += ["", "## Current Performance (last 30 days)"]
    if perf:
        lines += [
            f"- Occupancy: {perf.get('occupancy_pct', 'N/A')}%",
            f"- ADR: {fmt(perf.get('adr'))}",
            f"- RevPAR: {fmt(perf.get('revpar'))}",
            f"- Avg booking window: {perf.get('booking_window_days', 'N/A')} days",
            f"- Avg length of stay: {perf.get('avg_los', 'N/A')} nights",
            f"- Cancellation rate: {perf.get('cancellation_pct', 'N/A')}%",
            f"- Channel mix: Direct {perf.get('channel_direct_pct', 0)}% / "
            f"Booking.com {perf.get('channel_booking_pct', 0)}% / "
            f"Expedia {perf.get('channel_expedia_pct', 0)}% / "
            f"Airbnb {perf.get('channel_airbnb_pct', 0)}% / "
            f"Corporate {perf.get('channel_corp_pct', 0)}%",
            f"- Primary guest segment: {perf.get('guest_segment', 'N/A')}",
            f"- Top feeder markets: {perf.get('feeder_markets', 'N/A')}",
            f"- City average occupancy: {perf.get('city_avg_occ_pct', 'N/A')}%",
        ]
    else:
        lines.append("- No performance data provided. State all assumptions explicitly.")

    lines += ["", "## Market & Competitive Set"]
    if market:
        lines += [
            f"- Market average rate: {fmt(market.get('market_avg_rate'))}",
            f"- Current demand level: {market.get('demand_level', 'medium')}",
            f"- Seasonality pattern: {market.get('seasonality', 'N/A')}",
            f"- Upcoming events/holidays: {market.get('upcoming_events', 'N/A')}",
            f"- Key demand drivers: {market.get('demand_drivers', 'N/A')}",
        ]

    if compset:
        lines.append("- Competitive set (direct competitors):")
        for c in compset:
            lines.append(
                f"  * {c['name']} | type: {c.get('comp_type', 'N/A')} | "
                f"rooms: {c.get('rooms', 'N/A')} | "
                f"avg rate: {fmt(c.get('avg_rate'))} | "
                f"position vs us: {c.get('position', 'similar')}"
            )
    else:
        lines.append("- No competitor data provided. Use market knowledge for this area and property type.")

    # PMS raw data — highest value input, AI interprets any format
    pms_data = data.get('pms_raw_data', '') or prop.get('pms_raw_data', '')
    if pms_data and pms_data.strip():
        lines += [
            "",
            "## Raw PMS / OTA Report Data (interpret and extract all relevant metrics)",
            "The following is a direct export from the property's PMS or OTA extranet.",
            "Extract all relevant metrics: occupancy, ADR, RevPAR, booking pace, cancellations, etc.",
            "Use this data to make your analysis more precise and override assumptions where possible.",
            "```",
            pms_data.strip()[:3000],  # limit to 3000 chars
            "```",
        ]

    lines += [
        "",
        "Produce the complete 10-section OMNI-REVENUE analysis now. "
        f"All monetary amounts MUST be in {currency}. "
        "Be specific with numbers. No vague advice."
    ]

    return "\n".join(lines)


def parse_sections(raw: str) -> dict:
    sections = {}
    pattern = re.compile(r'(##\s+\d+\.\s+.+?)(?=\n##\s+\d+\.|\Z)', re.DOTALL)
    for match in pattern.finditer(raw):
        content = match.group(1).strip()
        num_match = re.match(r'##\s+(\d+)\.', content)
        if num_match:
            num = num_match.group(1)
            key = SECTION_MAP.get(num)
            if key:
                sections[key] = content
    return sections


def generate_omni_analysis(data: dict) -> dict:
    from groq import Groq

    api_key = os.environ.get('GROQ_API_KEY', '')
    if not api_key:
        raise ValueError("GROQ_API_KEY not configurado en variables de entorno.")

    client = Groq(api_key=api_key)
    prompt = build_property_prompt(data)

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {'role': 'system', 'content': OMNI_SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt}
        ],
        temperature=0.4,
        max_tokens=8192,
    )

    raw = response.choices[0].message.content
    sections = parse_sections(raw)
    return {'raw': raw, 'sections': sections}
