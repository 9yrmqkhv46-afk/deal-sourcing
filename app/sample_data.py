"""Bundled demo batch.

A LARGE, varied, thesis-aligned batch (~35 source items) that exercises every
branch of the investment thesis and all six source families. It is engineered
to produce a meaningful spread of outcomes so the dashboard looks full and the
top-lists are useful:

* Multiple ``core_thesis`` deals (preferred sector + 6yr+ trading history +
  in-range financials + long-tenured founder + automation upside).
* Several ``adjacent_thesis`` deals (one key filter unknown / weaker, or a
  partial-fit score in the 40-69 band, plus ESTIMATED price-range deals).
* Several ``reject`` deals: banned sectors (tobacco, liquor, gambling, vaping),
  clearly oversized (>50M EV) deals, and low-information / vague listings.
* At least one ``stale`` deal (dates older than the 12-month cutoff) which is
  classified but excluded from the top-deals list.
* At least one deal with no dates at all (``unknown_date``).

IMPORTANT: every record below is **illustrative demo data**. The businesses,
people, financials and contact details are fictional and are provided only to
showcase the pipeline - they must never be treated as real opportunities.

The batch is fully deterministic: no randomness is used. Listing dates are
generated relative to today so the freshest deals stay non-stale and naturally
populate the dashboard's top lists.
"""

from __future__ import annotations

import datetime as _dt

AUD = "AUD"


def _recent(months_ago: int) -> str:
    """Return an ISO date ``months_ago`` months before today (deterministic)."""

    today = _dt.date.today()
    month_index = (today.year * 12 + (today.month - 1)) - months_ago
    year, month = divmod(month_index, 12)
    return _dt.date(year, month + 1, min(today.day, 28)).isoformat()


def sample_batch() -> list[dict]:
    """Return the bundled demo batch as a list of source-item dicts."""

    return [
        # ===================================================================
        # MARKETPLACE - core-thesis manufacturing / processing / services
        # ===================================================================
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Established packaging manufacturer in Melbourne VIC. Long-standing "
                "B2B customer base, heavy reliance on manual bookkeeping and "
                "spreadsheet-based scheduling with clear automation upside. Owner "
                "retiring after building the business since 2002."
            ),
            "structured": {
                "title": "Established Packaging Manufacturer - VIC",
                "url": "https://scaling.com.au/listing/pkg-vic-1042",
                "description": (
                    "Profitable corrugated and flexible packaging maker supplying "
                    "food and beverage producers under multi-year supply agreements."
                ),
                "deal_type": "sale",
                "asking_price": 12_000_000,
                "asking_price_currency": AUD,
                "revenue": 4_200_000,
                "revenue_currency": AUD,
                "ebitda": 950_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Manual bookkeeping and spreadsheet scheduling present clear "
                    "automation upside across order-to-cash and production planning."
                ),
                "competitive_notes": (
                    "Sticky B2B contracts and regional logistics moat; limited "
                    "direct competition in flexible packaging for SME food brands."
                ),
                "listing_date": _recent(1),
                "last_seen_at": _recent(0),
                "location_text": "Melbourne, VIC, Australia",
                "company": {
                    "name": "Apex Packaging Pty Ltd",
                    "country": "Australia",
                    "state": "VIC",
                    "city": "Melbourne",
                    "sector": "manufacturing",
                    "subsector": "packaging",
                    "founded_year": 2002,
                    "employees": 45,
                },
                "founders": [
                    {
                        "name": "Margaret Doyle",
                        "role": "Founder",
                        "start_year": 2002,
                        "email": "margaret@apexpackaging.example.com.au",
                        "linkedin_url": "https://linkedin.com/in/margaret-doyle-demo",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "David Chen",
                        "role_or_title": "Broker",
                        "sector_focus": "manufacturing",
                        "deal_size_focus": "10-40M",
                        "region_or_state": "VIC",
                        "email": "david.chen@scaling.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Family-owned food-processing manufacturer in regional NSW. Recurring "
                "supermarket and food-service contracts. Production scheduling and "
                "invoicing are still manual spreadsheets - clear automation upside. "
                "Trading since 2000."
            ),
            "structured": {
                "title": "Regional Food-Processing Manufacturer - NSW",
                "url": "https://scalingup.com.au/listing/food-nsw-2208",
                "description": (
                    "Ready-meal and sauce manufacturer with private-label programs "
                    "for two national grocery chains."
                ),
                "deal_type": "sale",
                "asking_price": 22_000_000,
                "asking_price_currency": AUD,
                "revenue": 12_000_000,
                "revenue_currency": AUD,
                "ebitda": 2_400_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Manual scheduling and paper-based invoicing offer strong "
                    "automation upside in planning and accounts."
                ),
                "listing_date": _recent(2),
                "last_seen_at": _recent(0),
                "location_text": "Wagga Wagga, NSW, Australia",
                "company": {
                    "name": "Riverina Food Co",
                    "country": "Australia",
                    "state": "NSW",
                    "city": "Wagga Wagga",
                    "sector": "manufacturing",
                    "subsector": "food processing",
                    "founded_year": 2000,
                    "employees": 80,
                },
                "founders": [
                    {
                        "name": "Antonio Russo",
                        "role": "Founder",
                        "start_year": 1999,
                        "email": "antonio@riverinafood.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Profitable bookkeeping and accounting practice serving SMEs across "
                "metro Brisbane. Repetitive manual data entry and reconciliation "
                "workflows - significant automation upside. Established 2005."
            ),
            "structured": {
                "title": "Bookkeeping & Accounting Practice - QLD",
                "url": "https://scaling.com.au/listing/book-qld-3310",
                "deal_type": "sale",
                "asking_price": 15_000_000,
                "asking_price_currency": AUD,
                "revenue": 3_000_000,
                "revenue_currency": AUD,
                "ebitda": 800_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "High volume of repetitive data entry and reconciliation gives "
                    "clear automation upside via modern accounting automation."
                ),
                "listing_date": _recent(1),
                "last_seen_at": _recent(0),
                "location_text": "Brisbane, QLD, Australia",
                "company": {
                    "name": "Summit Bookkeeping Group",
                    "country": "Australia",
                    "state": "QLD",
                    "city": "Brisbane",
                    "sector": "bookkeeping",
                    "subsector": "accounting",
                    "founded_year": 2005,
                    "employees": 28,
                },
                "founders": [
                    {
                        "name": "Helen Tran",
                        "role": "Director",
                        "start_year": 2001,
                        "email": "helen.tran@summitbooks.example.com.au",
                        "linkedin_url": "https://linkedin.com/in/helen-tran-demo",
                    }
                ],
            },
        },
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "B2B professional services firm with recurring retainer revenue and "
                "blue-chip client base. Back-office and invoicing remain largely "
                "manual with automation upside. Operating since 2004."
            ),
            "structured": {
                "title": "B2B Professional Services Firm - VIC",
                "url": "https://scaling.com.au/listing/prof-vic-4417",
                "deal_type": "sale",
                "asking_price": 18_000_000,
                "asking_price_currency": AUD,
                "revenue": 6_000_000,
                "revenue_currency": AUD,
                "ebitda": 1_500_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Manual back-office and invoicing workflows present clear "
                    "automation upside."
                ),
                "listing_date": _recent(3),
                "last_seen_at": _recent(1),
                "location_text": "Melbourne, VIC, Australia",
                "company": {
                    "name": "Meridian Advisory Partners",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "professional services",
                    "founded_year": 2004,
                    "employees": 52,
                },
                "founders": [
                    {
                        "name": "Geoffrey Hale",
                        "role": "Partner",
                        "start_year": 2002,
                        "linkedin_url": "https://linkedin.com/in/geoffrey-hale-demo",
                    }
                ],
            },
        },
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Commercial facilities-services business with recurring cleaning and "
                "maintenance contracts across SA. Scheduling and timesheets are "
                "manual - strong automation upside. Founded 2008."
            ),
            "structured": {
                "title": "Commercial Facilities Services - SA",
                "url": "https://scalingup.com.au/listing/fac-sa-5521",
                "deal_type": "sale",
                "asking_price": 30_000_000,
                "asking_price_currency": AUD,
                "revenue": 20_000_000,
                "revenue_currency": AUD,
                "ebitda": 3_000_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Manual scheduling and timesheet handling offer clear automation "
                    "upside in workforce management and billing."
                ),
                "listing_date": _recent(2),
                "last_seen_at": _recent(0),
                "location_text": "Adelaide, SA, Australia",
                "company": {
                    "name": "Coastal Facilities Management",
                    "country": "Australia",
                    "state": "SA",
                    "sector": "facilities services",
                    "founded_year": 2008,
                    "employees": 210,
                },
                "founders": [
                    {
                        "name": "Daniela Ferreira",
                        "role": "Founder",
                        "start_year": 2005,
                        "email": "daniela@coastalfm.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Managed IT services provider with recurring monthly contracts for "
                "SME clients. Ticketing and onboarding are repetitive and manual - "
                "automation upside. Established 2007."
            ),
            "structured": {
                "title": "Managed IT Services Provider - NSW",
                "url": "https://scaling.com.au/listing/it-nsw-6634",
                "deal_type": "sale",
                "asking_price": 28_000_000,
                "asking_price_currency": AUD,
                "revenue": 9_000_000,
                "revenue_currency": AUD,
                "ebitda": 2_200_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Repetitive manual ticketing and client onboarding present clear "
                    "automation upside."
                ),
                "listing_date": _recent(1),
                "last_seen_at": _recent(0),
                "location_text": "Sydney, NSW, Australia",
                "company": {
                    "name": "BlueScope Managed Services",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "it services",
                    "subsector": "managed services",
                    "founded_year": 2007,
                    "employees": 64,
                },
                "founders": [
                    {
                        "name": "Rajesh Kumar",
                        "role": "Founder",
                        "start_year": 2004,
                        "email": "rajesh@bluescopems.example.com.au",
                        "linkedin_url": "https://linkedin.com/in/rajesh-kumar-demo",
                    }
                ],
            },
        },
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Industrial maintenance and engineering services group in WA with "
                "long-term plant contracts. Manual job-scheduling and back-office "
                "data entry - clear automation upside. Trading since 2006."
            ),
            "structured": {
                "title": "Industrial Services Group - WA",
                "url": "https://scalingup.com.au/listing/ind-wa-7740",
                "deal_type": "sale",
                "asking_price": 24_000_000,
                "asking_price_currency": AUD,
                "revenue": 11_000_000,
                "revenue_currency": AUD,
                "ebitda": 2_100_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Manual job-scheduling and back-office data entry give clear "
                    "automation upside."
                ),
                "listing_date": _recent(2),
                "last_seen_at": _recent(1),
                "location_text": "Perth, WA, Australia",
                "company": {
                    "name": "Geelong Industrial Services",
                    "country": "Australia",
                    "state": "WA",
                    "sector": "industrial services",
                    "founded_year": 2006,
                    "employees": 130,
                },
                "founders": [
                    {
                        "name": "Brett Lawson",
                        "role": "Founder",
                        "start_year": 2004,
                        "email": "brett@geelongindustrial.example.com.au",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "Nina Petrova",
                        "role_or_title": "Broker",
                        "sector_focus": "industrial services",
                        "deal_size_focus": "20-50M",
                        "region_or_state": "WA",
                        "email": "nina.petrova@scalingup.example.com.au",
                    }
                ],
            },
        },
        # ===================================================================
        # MARKETPLACE - franchises with unit economics
        # ===================================================================
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Accounting franchise network for sale - franchisor plus company-owned "
                "units. Repetitive manual compliance workflows across the network mean "
                "clear automation upside. Established 2003."
            ),
            "structured": {
                "title": "Accounting Franchise Network - National",
                "url": "https://scaling.com.au/listing/fran-acc-8810",
                "is_franchise": True,
                "asking_price": 26_000_000,
                "asking_price_currency": AUD,
                "revenue": 14_000_000,
                "revenue_currency": AUD,
                "ebitda": 3_100_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Repetitive manual compliance and bookkeeping across franchise "
                    "units present clear automation upside."
                ),
                "competitive_notes": (
                    "Franchise unit economics: 42 units, average unit revenue ~A$640k, "
                    "ongoing royalty 8% of unit revenue plus 2% marketing levy, "
                    "franchisor EBITDA margin ~22%. Strong brand vs independent firms."
                ),
                "description": (
                    "Unit economics - royalties 8%, marketing levy 2%, average unit "
                    "revenue A$640k, network of 42 franchised offices."
                ),
                "listing_date": _recent(2),
                "last_seen_at": _recent(0),
                "location_text": "Sydney, NSW, Australia",
                "company": {
                    "name": "Tasman Accounting Franchising",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "accounting",
                    "founded_year": 2003,
                    "employees": 90,
                },
                "founders": [
                    {
                        "name": "Patricia Nguyen",
                        "role": "Founder",
                        "start_year": 2001,
                        "email": "patricia@tasmanfranchising.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Bookkeeping franchise unit for sale within a national brand. Solid "
                "recurring client base; franchisee retiring after running it since 2012."
            ),
            "structured": {
                "title": "Bookkeeping Franchise Unit - VIC",
                "url": "https://scalingup.com.au/listing/fran-book-9912",
                "is_franchise": True,
                "asking_price": 9_000_000,
                "asking_price_currency": AUD,
                "revenue": 2_500_000,
                "revenue_currency": AUD,
                "ebitda": 600_000,
                "ebitda_currency": AUD,
                "competitive_notes": (
                    "Franchise unit economics: royalty 7% of revenue, average client "
                    "fee A$420/month, ~210 recurring clients, EBITDA margin ~24%."
                ),
                "description": (
                    "Single-territory franchise. Royalty 7%, ~210 recurring clients, "
                    "average monthly fee A$420."
                ),
                "listing_date": _recent(4),
                "last_seen_at": _recent(1),
                "location_text": "Geelong, VIC, Australia",
                "company": {
                    "name": "LedgerLine Franchise (Geelong)",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "bookkeeping",
                    "founded_year": 2012,
                    "employees": 9,
                },
                "founders": [
                    {
                        "name": "Karen Mills",
                        "role": "Director",
                        "start_year": 2012,
                        "email": "karen.mills@ledgerline.example.com.au",
                    }
                ],
            },
        },
        # ===================================================================
        # MARKETPLACE - price-range-only (ESTIMATED) -> adjacent
        # ===================================================================
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Packaging components manufacturer in QLD. Price guidance only; "
                "financials available under NDA. Operating since 2009."
            ),
            "structured": {
                "title": "Packaging Components Manufacturer - QLD",
                "url": "https://scaling.com.au/listing/pkg-qld-1313",
                "deal_type": "sale",
                "asking_price": [8_000_000, 12_000_000],
                "asking_price_currency": AUD,
                "listing_date": _recent(3),
                "last_seen_at": _recent(1),
                "location_text": "Toowoomba, QLD, Australia",
                "company": {
                    "name": "Darling Downs Packaging",
                    "country": "Australia",
                    "state": "QLD",
                    "sector": "manufacturing",
                    "subsector": "packaging",
                    "founded_year": 2009,
                },
            },
        },
        # ===================================================================
        # MARKETPLACE - missing financials -> unknown bucket / low score
        # ===================================================================
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Suburban retail store for sale. Limited information provided; no "
                "financials disclosed."
            ),
            "structured": {
                "title": "Suburban Retail Store - VIC",
                "url": "https://scalingup.com.au/listing/ret-vic-1414",
                "deal_type": "sale",
                "listing_date": _recent(2),
                "location_text": "Bendigo, VIC, Australia",
                "company": {
                    "name": "Bendigo Corner Retail",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "retail",
                    "founded_year": 2016,
                },
            },
        },
        # ===================================================================
        # MARKETPLACE - oversized -> reject
        # ===================================================================
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Large national logistics and warehousing operator. Asset-heavy fleet "
                "and warehouse network with strong recurring contracts."
            ),
            "structured": {
                "title": "National Logistics Operator - Major Scale",
                "url": "https://scalingup.com.au/listing/logi-9001",
                "deal_type": "sale",
                "asking_price": 85_000_000,
                "asking_price_currency": AUD,
                "revenue": 60_000_000,
                "revenue_currency": AUD,
                "ebitda": 9_000_000,
                "ebitda_currency": AUD,
                "listing_date": _recent(2),
                "last_seen_at": _recent(1),
                "location_text": "Sydney, NSW, Australia",
                "company": {
                    "name": "Continental Logistics Holdings",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "logistics",
                    "founded_year": 1998,
                },
            },
        },
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Mid-market manufacturing group with multiple plants. Strong margins "
                "but enterprise value well above our absolute ceiling."
            ),
            "structured": {
                "title": "Multi-Plant Manufacturing Group - National",
                "url": "https://scaling.com.au/listing/mfg-grp-1515",
                "deal_type": "sale",
                "asking_price": 62_000_000,
                "asking_price_currency": AUD,
                "revenue": 40_000_000,
                "revenue_currency": AUD,
                "ebitda": 7_000_000,
                "ebitda_currency": AUD,
                "listing_date": _recent(3),
                "last_seen_at": _recent(1),
                "location_text": "Melbourne, VIC, Australia",
                "company": {
                    "name": "National Manufacturing Group",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "manufacturing",
                    "founded_year": 2001,
                },
            },
        },
        # ===================================================================
        # MARKETPLACE - banned sectors -> reject
        # ===================================================================
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Tobacco and cigarette wholesale distribution business with national "
                "retail accounts."
            ),
            "structured": {
                "title": "Tobacco & Cigarette Distribution",
                "url": "https://scaling.com.au/listing/tob-1616",
                "deal_type": "sale",
                "asking_price": 14_000_000,
                "asking_price_currency": AUD,
                "revenue": 9_000_000,
                "revenue_currency": AUD,
                "ebitda": 1_300_000,
                "ebitda_currency": AUD,
                "listing_date": _recent(1),
                "last_seen_at": _recent(0),
                "location_text": "Sydney, NSW, Australia",
                "company": {
                    "name": "Harbour Tobacco Distribution",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "tobacco",
                    "founded_year": 2004,
                },
            },
        },
        {
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Craft brewery and liquor wholesale operation with established "
                "distribution into pubs and bottle shops."
            ),
            "structured": {
                "title": "Craft Brewery & Liquor Wholesale",
                "url": "https://scalingup.com.au/listing/liq-1717",
                "deal_type": "sale",
                "asking_price": 16_000_000,
                "asking_price_currency": AUD,
                "revenue": 8_500_000,
                "revenue_currency": AUD,
                "ebitda": 1_400_000,
                "ebitda_currency": AUD,
                "listing_date": _recent(2),
                "last_seen_at": _recent(0),
                "location_text": "Brisbane, QLD, Australia",
                "company": {
                    "name": "Riverbank Brewery",
                    "country": "Australia",
                    "state": "QLD",
                    "sector": "brewery",
                    "subsector": "liquor",
                    "founded_year": 2010,
                },
            },
        },
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Retail chain of vaping and e-cigarette stores across metro locations."
            ),
            "structured": {
                "title": "Vaping Retail Chain",
                "url": "https://scaling.com.au/listing/vape-1818",
                "deal_type": "sale",
                "asking_price": 7_000_000,
                "asking_price_currency": AUD,
                "revenue": 5_000_000,
                "revenue_currency": AUD,
                "ebitda": 700_000,
                "ebitda_currency": AUD,
                "listing_date": _recent(1),
                "last_seen_at": _recent(0),
                "location_text": "Perth, WA, Australia",
                "company": {
                    "name": "CloudNine Vaping Retail",
                    "country": "Australia",
                    "state": "WA",
                    "sector": "vaping",
                    "founded_year": 2018,
                },
            },
        },
        # ===================================================================
        # MARKETPLACE - stale (would be core, but excluded from top deals)
        # ===================================================================
        {
            "source_name": "scaling.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Heritage packaging manufacturer (archived listing). Manual bookkeeping "
                "and scheduling with clear automation upside. Trading since 2001."
            ),
            "structured": {
                "title": "Heritage Packaging Manufacturer (archived)",
                "url": "https://scaling.com.au/listing/pkg-old-1919",
                "deal_type": "sale",
                "asking_price": 16_000_000,
                "asking_price_currency": AUD,
                "revenue": 7_000_000,
                "revenue_currency": AUD,
                "ebitda": 1_600_000,
                "ebitda_currency": AUD,
                "ai_automation_potential_notes": (
                    "Manual bookkeeping and scheduling give clear automation upside."
                ),
                "listing_date": _recent(16),
                "last_seen_at": _recent(15),
                "location_text": "Newcastle, NSW, Australia",
                "company": {
                    "name": "Heritage Packaging Co",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "manufacturing",
                    "subsector": "packaging",
                    "founded_year": 2001,
                },
                "founders": [
                    {
                        "name": "Ronald Webb",
                        "role": "Founder",
                        "start_year": 2000,
                        "email": "ronald@heritagepackaging.example.com.au",
                    }
                ],
            },
        },
        # ===================================================================
        # BROKER_DIRECTORY - high-priority intermediary contacts
        # ===================================================================
        {
            "source_name": "Acquire Partners",
            "source_type": "broker_directory",
            "raw_text": (
                "Industrial M&A brokerage representing a precision manufacturing "
                "business in NSW. Recurring OEM contracts."
            ),
            "structured": {
                "title": "Precision Manufacturing Business (broker-represented) - NSW",
                "url": "https://acquirepartners.example.com.au/deals/pm-nsw",
                "deal_type": "sale",
                "asking_price": 17_000_000,
                "asking_price_currency": AUD,
                "revenue": 5_000_000,
                "revenue_currency": AUD,
                "ebitda": 1_200_000,
                "ebitda_currency": AUD,
                "listing_date": _recent(2),
                "last_seen_at": _recent(0),
                "location_text": "Newcastle, NSW, Australia",
                "company": {
                    "name": "Precision Components NSW",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "manufacturing",
                    "founded_year": 2006,
                },
                "contacts": [
                    {
                        "person_or_org_name": "Sarah Whitman",
                        "role_or_title": "Broker",
                        "sector_focus": "manufacturing & industrials",
                        "deal_size_focus": "10-50M",
                        "region_or_state": "NSW",
                        "email": "sarah.whitman@acquirepartners.example.com.au",
                        "linkedin_url": "https://linkedin.com/in/sarah-whitman-demo",
                    }
                ],
            },
        },
        {
            "source_name": "Meridian Business Brokers",
            "source_type": "broker_directory",
            "raw_text": (
                "Business brokerage specialising in professional-services practices "
                "across Victoria. Deal sizes 10-30M."
            ),
            "structured": {
                "title": "Meridian Business Brokers - Practice Listings",
                "url": "https://meridianbrokers.example.com.au",
                "location_text": "Melbourne, VIC, Australia",
                "company": {
                    "name": "Meridian Business Brokers",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "professional services",
                },
                "contacts": [
                    {
                        "person_or_org_name": "Tom Alder",
                        "role_or_title": "Broker",
                        "sector_focus": "professional services",
                        "deal_size_focus": "10-30M",
                        "region_or_state": "VIC",
                        "email": "tom.alder@meridianbrokers.example.com.au",
                        "phone": "+61 3 5550 7788",
                    }
                ],
            },
        },
        {
            "source_name": "Pinnacle Deal Advisory",
            "source_type": "broker_directory",
            "raw_text": (
                "Boutique advisory focused on bookkeeping and accounting roll-ups in "
                "Queensland. Deal sizes 15-50M."
            ),
            "structured": {
                "title": "Pinnacle Deal Advisory - Accounting Roll-ups",
                "url": "https://pinnacleadvisory.example.com.au",
                "location_text": "Brisbane, QLD, Australia",
                "company": {
                    "name": "Pinnacle Deal Advisory",
                    "country": "Australia",
                    "state": "QLD",
                    "sector": "accounting",
                },
                "contacts": [
                    {
                        "person_or_org_name": "Rebecca Lyle",
                        "role_or_title": "Broker",
                        "sector_focus": "bookkeeping & accounting",
                        "deal_size_focus": "15-50M",
                        "region_or_state": "QLD",
                        "email": "rebecca.lyle@pinnacleadvisory.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "NSW Business Brokers Network",
            "source_type": "broker_directory",
            "raw_text": (
                "Brokerage network covering manufacturing and industrial businesses "
                "throughout NSW. Deal sizes 20-50M."
            ),
            "structured": {
                "title": "NSW Business Brokers Network",
                "url": "https://nswbrokers.example.com.au",
                "location_text": "Sydney, NSW, Australia",
                "company": {
                    "name": "NSW Business Brokers Network",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "manufacturing",
                },
                "contacts": [
                    {
                        "person_or_org_name": "Olivia Grant",
                        "role_or_title": "Broker",
                        "sector_focus": "manufacturing",
                        "deal_size_focus": "20-50M",
                        "region_or_state": "NSW",
                        "email": "olivia.grant@nswbrokers.example.com.au",
                        "linkedin_url": "https://linkedin.com/in/olivia-grant-demo",
                    }
                ],
            },
        },
        # ===================================================================
        # INSOLVENCY_PLATFORM - distress deals + practitioner contacts
        # ===================================================================
        {
            "source_name": "ASIC Published Notices",
            "source_type": "insolvency_platform",
            "raw_text": (
                "Appointment of liquidator for a regional engineering services firm "
                "with recurring maintenance contracts. Restructuring opportunity for "
                "credit buyers."
            ),
            "structured": {
                "title": "Engineering Services Firm - Voluntary Administration",
                "url": "https://insolvencynotices.asic.gov.au/notice/77231",
                "listing_date": _recent(2),
                "last_seen_at": _recent(1),
                "location_text": "Newcastle, NSW, Australia",
                "revenue": 1_800_000,
                "revenue_currency": AUD,
                "ebitda": 300_000,
                "ebitda_currency": AUD,
                "company": {
                    "name": "Hunter Engineering Services",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "engineering services",
                    "founded_year": 2011,
                },
                "contacts": [
                    {
                        "person_or_org_name": "Priya Nair",
                        "role_or_title": "Practitioner",
                        "sector_focus": "industrial insolvency",
                        "region_or_state": "NSW",
                        "email": "priya.nair@restructure.example.com.au",
                        "phone": "+61 2 5550 1234",
                    }
                ],
            },
        },
        {
            "source_name": "ASIC Published Notices",
            "source_type": "insolvency_platform",
            "raw_text": (
                "Liquidator appointed to a manufacturing business in WA with "
                "recurring supply agreements; wind-down sale of the business and "
                "customer contracts."
            ),
            "structured": {
                "title": "Manufacturing Business - Liquidation (WA)",
                "url": "https://insolvencynotices.asic.gov.au/notice/77890",
                "listing_date": _recent(3),
                "last_seen_at": _recent(1),
                "location_text": "Perth, WA, Australia",
                "revenue": 2_200_000,
                "revenue_currency": AUD,
                "ebitda": 400_000,
                "ebitda_currency": AUD,
                "company": {
                    "name": "Westland Manufacturing",
                    "country": "Australia",
                    "state": "WA",
                    "sector": "manufacturing",
                    "founded_year": 2009,
                },
                "contacts": [
                    {
                        "person_or_org_name": "Angela Foster",
                        "role_or_title": "Practitioner",
                        "sector_focus": "manufacturing distress",
                        "region_or_state": "WA",
                        "email": "angela.foster@insolvencywa.example.com.au",
                        "phone": "+61 8 5550 4321",
                    }
                ],
            },
        },
        {
            "source_name": "AFSA Trustee Register",
            "source_type": "insolvency_platform",
            "raw_text": (
                "Trustee appointed over a freight and logistics SME in VIC. Recurring "
                "contracted routes; sale of business as a going concern under review."
            ),
            "structured": {
                "title": "Freight & Logistics SME - Trustee Sale (VIC)",
                "url": "https://afsa.gov.au/trustee/notice/55112",
                "listing_date": _recent(4),
                "last_seen_at": _recent(2),
                "location_text": "Melbourne, VIC, Australia",
                "revenue": 2_000_000,
                "revenue_currency": AUD,
                "ebitda": 350_000,
                "ebitda_currency": AUD,
                "company": {
                    "name": "Metro Freight Lines",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "logistics",
                    "founded_year": 2012,
                },
                "contacts": [
                    {
                        "person_or_org_name": "Daniel Cho",
                        "role_or_title": "Practitioner",
                        "sector_focus": "SME distress",
                        "region_or_state": "VIC",
                        "email": "daniel.cho@afsatrustee.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "AFSA Trustee Register",
            "source_type": "insolvency_platform",
            "raw_text": (
                "Trustee appointed over a small retail group in SA. Limited financial "
                "disclosure at this stage."
            ),
            "structured": {
                "title": "Small Retail Group - Trustee Appointment (SA)",
                "url": "https://afsa.gov.au/trustee/notice/55998",
                "listing_date": _recent(2),
                "location_text": "Adelaide, SA, Australia",
                "company": {
                    "name": "Adelaide Retail Group",
                    "country": "Australia",
                    "state": "SA",
                    "sector": "retail",
                    "founded_year": 2013,
                },
                "contacts": [
                    {
                        "person_or_org_name": "Mark Renshaw",
                        "role_or_title": "Practitioner",
                        "sector_focus": "SME distress",
                        "region_or_state": "SA",
                        "email": "mark.renshaw@afsatrustee.example.com.au",
                    }
                ],
            },
        },
        # ===================================================================
        # CHAMBER_DIRECTORY - off-market targets + association officials
        # ===================================================================
        {
            "source_name": "Victorian Chamber of Commerce",
            "source_type": "chamber_directory",
            "raw_text": (
                "Member firm directory entry for a bookkeeping and accounting practice "
                "serving SMEs across regional Victoria. Repetitive manual data entry "
                "and invoicing workflows."
            ),
            "structured": {
                "title": "Regional Bookkeeping & Accounting Practice",
                "url": "https://victorianchamber.example.com.au/members/reg-bookkeeping",
                "ai_automation_potential_notes": (
                    "Repetitive manual data entry and invoicing present clear "
                    "automation upside."
                ),
                "listing_date": _recent(3),
                "location_text": "Ballarat, VIC, Australia",
                "company": {
                    "name": "Ballarat Books & Advisory",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "bookkeeping",
                    "founded_year": 2009,
                },
                "founders": [
                    {
                        "name": "Stephen Park",
                        "role": "Director",
                        "start_year": 2009,
                        "linkedin_url": "https://linkedin.com/in/stephen-park-demo",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "Janet Wills",
                        "role_or_title": "Association Official",
                        "sector_focus": "professional services",
                        "region_or_state": "VIC",
                        "email": "janet.wills@victorianchamber.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "Brisbane Manufacturers Association",
            "source_type": "chamber_directory",
            "raw_text": (
                "Association member profile: established manufacturing firm, owner "
                "approaching retirement. Manual production scheduling and back-office "
                "processes. (No listing dates provided.)"
            ),
            "structured": {
                "title": "Off-market Manufacturing Member Firm - QLD",
                "url": "https://brismanufacturers.example.com.au/members/firm-204",
                "ai_automation_potential_notes": (
                    "Manual production scheduling and back-office processes present "
                    "clear automation upside."
                ),
                "location_text": "Brisbane, QLD, Australia",
                "company": {
                    "name": "Brisbane Precision Manufacturing",
                    "country": "Australia",
                    "state": "QLD",
                    "sector": "manufacturing",
                    "founded_year": 2007,
                },
                "contacts": [
                    {
                        "person_or_org_name": "Greg Sandhu",
                        "role_or_title": "Association Official",
                        "sector_focus": "manufacturing",
                        "region_or_state": "QLD",
                        "email": "greg.sandhu@brismanufacturers.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "Perth Accounting Guild",
            "source_type": "chamber_directory",
            "raw_text": (
                "Guild directory entry for an established accounting firm. Long-tenured "
                "managing partner. Manual compliance workflows with automation upside."
            ),
            "structured": {
                "title": "Off-market Accounting Firm - WA",
                "url": "https://perthaccountingguild.example.com.au/members/firm-77",
                "ai_automation_potential_notes": (
                    "Manual compliance workflows present clear automation upside."
                ),
                "listing_date": _recent(5),
                "location_text": "Perth, WA, Australia",
                "company": {
                    "name": "Swan River Accounting",
                    "country": "Australia",
                    "state": "WA",
                    "sector": "accounting",
                    "founded_year": 2005,
                },
                "founders": [
                    {
                        "name": "Malcolm Reid",
                        "role": "Partner",
                        "start_year": 2004,
                        "email": "malcolm.reid@swanriveracct.example.com.au",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "Susan Doyle",
                        "role_or_title": "Association Official",
                        "sector_focus": "accounting",
                        "region_or_state": "WA",
                        "email": "susan.doyle@perthaccountingguild.example.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "Adelaide Chamber of Commerce",
            "source_type": "chamber_directory",
            "raw_text": (
                "Member profile for an engineering services firm with a long-tenured "
                "founder. Manual job scheduling and data entry - automation upside."
            ),
            "structured": {
                "title": "Off-market Engineering Services Firm - SA",
                "url": "https://adelaidechamber.example.com.au/members/firm-318",
                "ai_automation_potential_notes": (
                    "Manual job scheduling and data entry present clear automation "
                    "upside."
                ),
                "listing_date": _recent(6),
                "location_text": "Adelaide, SA, Australia",
                "company": {
                    "name": "Torrens Engineering",
                    "country": "Australia",
                    "state": "SA",
                    "sector": "engineering services",
                    "founded_year": 2010,
                },
                "founders": [
                    {
                        "name": "Helen Marsh",
                        "role": "Founder",
                        "start_year": 2003,
                        "email": "helen.marsh@torrenseng.example.com.au",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "Peter Hollis",
                        "role_or_title": "Association Official",
                        "sector_focus": "engineering",
                        "region_or_state": "SA",
                        "email": "peter.hollis@adelaidechamber.example.com.au",
                    }
                ],
            },
        },
        # ===================================================================
        # SOCIAL - posts (hype is NOT financial evidence)
        # ===================================================================
        {
            "source_name": "LinkedIn",
            "source_type": "social",
            "raw_text": (
                "Exciting growth! Our casino and sports-betting gaming venue group is "
                "expanding across the east coast. DM to learn about investment."
            ),
            "structured": {
                "title": "Casino & Sports Betting Venue Group - Expansion",
                "url": "https://linkedin.com/posts/gaming-group-expansion-demo",
                "listing_date": _recent(1),
                "location_text": "Gold Coast, QLD, Australia",
                "company": {
                    "name": "EastCoast Gaming Group",
                    "country": "Australia",
                    "state": "QLD",
                    "sector": "gambling",
                },
            },
        },
        {
            "source_name": "LinkedIn",
            "source_type": "social",
            "raw_text": (
                "Broker post: seeing strong demand for sub-30M manufacturing deals. "
                "One VIC maker (manual scheduling, big automation upside) quietly "
                "exploring a sale. Claims of 'huge revenue' - unverified."
            ),
            "structured": {
                "title": "Broker post: sub-30M manufacturing deal flow",
                "url": "https://linkedin.com/posts/broker-mfg-demo",
                "revenue": 25_000_000,
                "revenue_currency": AUD,
                "listing_date": _recent(1),
                "location_text": "Melbourne, VIC, Australia",
                "company": {
                    "name": "Undisclosed VIC Manufacturer",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "manufacturing",
                    "founded_year": 2010,
                },
                "contacts": [
                    {
                        "person_or_org_name": "James Pearce",
                        "role_or_title": "Broker",
                        "sector_focus": "manufacturing",
                        "deal_size_focus": "10-30M",
                        "region_or_state": "VIC",
                        "linkedin_url": "https://linkedin.com/in/james-pearce-demo",
                    }
                ],
            },
        },
        {
            "source_name": "X",
            "source_type": "social",
            "raw_text": (
                "Founder thread: thinking about selling our logistics tech business. "
                "Manual dispatch still everywhere - automation upside is real. "
                "Bootstrapped to '$5M revenue' (their words)."
            ),
            "structured": {
                "title": "Founder thread: logistics business possibly for sale",
                "url": "https://x.com/posts/founder-logistics-demo",
                "revenue": 5_000_000,
                "revenue_currency": AUD,
                "listing_date": _recent(2),
                "location_text": "Sydney, NSW, Australia",
                "company": {
                    "name": "DispatchWorks",
                    "country": "Australia",
                    "state": "NSW",
                    "sector": "logistics",
                    "founded_year": 2015,
                },
            },
        },
        # ===================================================================
        # NEWS - RSS / news items on small / mid-market deals
        # ===================================================================
        {
            "source_name": "Australian Financial Review",
            "source_type": "news",
            "raw_text": (
                "Mid-market manufacturing M&A is heating up, with a regional VIC maker "
                "reportedly fielding offers. Insiders note manual back-office systems "
                "and clear automation upside."
            ),
            "structured": {
                "title": "Mid-market manufacturing M&A heats up",
                "url": "https://afr.example.com/news/mfg-ma-2026",
                "listing_date": _recent(1),
                "location_text": "Geelong, VIC, Australia",
                "company": {
                    "name": "Profiled VIC Manufacturer",
                    "country": "Australia",
                    "state": "VIC",
                    "sector": "manufacturing",
                    "founded_year": 2003,
                },
            },
        },
        {
            "source_name": "SmartCompany",
            "source_type": "news",
            "raw_text": (
                "An SME accounting roll-up is gathering pace in QLD. Founders cite "
                "manual compliance workflows and automation upside as the prize."
            ),
            "structured": {
                "title": "SME accounting roll-up gathers pace in QLD",
                "url": "https://smartcompany.example.com/news/acct-rollup-2026",
                "listing_date": _recent(2),
                "location_text": "Brisbane, QLD, Australia",
                "company": {
                    "name": "Profiled QLD Accounting Firm",
                    "country": "Australia",
                    "state": "QLD",
                    "sector": "accounting",
                    "founded_year": 2008,
                },
            },
        },
        {
            "source_name": "Industry Wire",
            "source_type": "news",
            "raw_text": (
                "Brief market wrap covering several unrelated sectors. No specific "
                "business, financials or location identified."
            ),
            "structured": {
                "title": "Weekly market wrap",
                "url": "https://industrywire.example.com/news/wrap-2026",
            },
        },
    ]
