"""Bundled demo batch.

A small, varied batch that exercises multiple source families and produces a mix
of classifications (at least one ``core_thesis`` and one ``reject``). Listing
dates are generated relative to today so the freshest deals stay non-stale and
populate the dashboard's top lists.
"""

from __future__ import annotations

import datetime as _dt


def _recent(months_ago: int) -> str:
    today = _dt.date.today()
    month_index = (today.year * 12 + (today.month - 1)) - months_ago
    year, month = divmod(month_index, 12)
    return _dt.date(year, month + 1, min(today.day, 28)).isoformat()


def sample_batch() -> list[dict]:
    """Return the bundled demo batch as a list of source-item dicts."""

    return [
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
                "deal_type": "sale",
                "asking_price": 12_000_000,
                "asking_price_currency": "AUD",
                "revenue": 4_200_000,
                "revenue_currency": "AUD",
                "ebitda": 950_000,
                "ebitda_currency": "AUD",
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
                        "email": "margaret@apexpackaging.com.au",
                        "linkedin_url": "https://linkedin.com/in/margaret-doyle",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "David Chen",
                        "role_or_title": "Broker",
                        "sector_focus": "manufacturing",
                        "deal_size_focus": "10-40M",
                        "region_or_state": "VIC",
                        "email": "david.chen@scaling.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "ASIC Published Notices",
            "source_type": "insolvency_platform",
            "raw_text": (
                "Appointment of liquidator for a regional engineering services firm. "
                "Recurring maintenance contracts; back-office processes are largely "
                "manual. Restructuring opportunity for credit buyers."
            ),
            "structured": {
                "title": "Engineering Services Firm - Voluntary Administration",
                "url": "https://insolvencynotices.asic.gov.au/notice/77231",
                "listing_date": _recent(2),
                "last_seen_at": _recent(1),
                "location_text": "Newcastle, NSW, Australia",
                "ebitda": 300_000,
                "ebitda_currency": "AUD",
                "revenue": 1_800_000,
                "revenue_currency": "AUD",
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
                        "email": "priya.nair@restructure.com.au",
                        "phone": "+61 2 5550 1234",
                    }
                ],
            },
        },
        {
            "source_name": "Victorian Chamber of Commerce",
            "source_type": "chamber_directory",
            "raw_text": (
                "Member firm directory entry for a bookkeeping and accounting "
                "practice serving SMEs across regional Victoria. Repetitive manual "
                "data entry and invoicing workflows."
            ),
            "structured": {
                "title": "Regional Bookkeeping & Accounting Practice",
                "url": "https://victorianchamber.com.au/members/reg-bookkeeping",
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
                        "linkedin_url": "https://linkedin.com/in/stephen-park-cpa",
                    }
                ],
                "contacts": [
                    {
                        "person_or_org_name": "Janet Wills",
                        "role_or_title": "Association Official",
                        "sector_focus": "professional services",
                        "region_or_state": "VIC",
                        "email": "janet.wills@victorianchamber.com.au",
                    }
                ],
            },
        },
        {
            "source_name": "LinkedIn",
            "source_type": "social",
            "raw_text": (
                "Exciting growth! Our casino and sports betting gaming venue group "
                "is expanding across the east coast. DM to learn about investment."
            ),
            "structured": {
                "title": "Casino & Sports Betting Venue Group - Expansion",
                "url": "https://linkedin.com/posts/gaming-group-expansion",
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
            "source_name": "scalingup.com.au",
            "source_type": "marketplace",
            "raw_text": (
                "Large national logistics and warehousing operator. Asset-heavy "
                "fleet and warehouse network. Strong recurring contracts."
            ),
            "structured": {
                "title": "National Logistics Operator - Major Scale",
                "url": "https://scalingup.com.au/listing/logi-9001",
                "deal_type": "sale",
                "asking_price": 85_000_000,
                "asking_price_currency": "AUD",
                "revenue": 60_000_000,
                "revenue_currency": "AUD",
                "ebitda": 9_000_000,
                "ebitda_currency": "AUD",
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
    ]
