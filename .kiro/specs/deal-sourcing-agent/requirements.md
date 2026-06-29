# Requirements Document

## Introduction

The Deal-Sourcing & CRM Enrichment Agent ("TransformBiz") is a deterministic, batch-oriented
processing engine for an investment/credit team. It accepts a batch of **pre-fetched** source
items (each carrying `source_name`, `source_type`, and `raw_text`), routes each item to a
source-type-specific handler, normalizes the content into structured entities, applies a documented
investment thesis (age, sector, financial, founder, and AI-automation filters), scores and
classifies each opportunity, extracts contacts and relationship leads, and emits a single **strict
JSON** object consumed by a downstream ETL that writes to a database and CRM.

The agent is intentionally **non-scraping**: it never fetches live websites. Its only inputs are the
batch it is given plus an injected configuration; its only output is the JSON contract. Two design
principles govern all behavior: **never fabricate data** (prefer `null` / `"unknown"` /
`"unknown_date"` over guessing) and **enforce exclusions strictly** (tobacco, liquor/alcohol-as-core,
and gambling are always rejected; deals clearly above the absolute maximum enterprise value are always
rejected). Scoring is conservative: ambiguity lowers the score rather than raising it, and marketing
hype is never treated as financial evidence.

These requirements are derived from the approved design document and are organized so that every
acceptance criterion is precise and verifiable, with the property-oriented criteria suitable for
property-based testing.

## Glossary

- **Agent**: The complete Deal-Sourcing & CRM Enrichment Agent that transforms a batch into the strict JSON output contract.
- **Ingestion_Loader**: The component that validates the incoming batch structure and each `SourceItem`.
- **Source_Router**: The component that dispatches each `SourceItem` to a handler based on `source_type`.
- **Source_Handler**: A source-type-specific component that extracts uniform `RawFields` and contacts from a `SourceItem` without inventing data.
- **Normalizer**: The component that converts `RawFields` into typed entity fields and performs conservative inference.
- **Scoring_Engine**: The component that evaluates thesis filters and computes the `overall_score`.
- **Classifier**: The component that assigns a `classification` of `core_thesis`, `adjacent_thesis`, or `reject`.
- **Contact_Extractor**: The component that builds `Contact` records and annotates relevance and outreach priority.
- **Output_Assembler**: The component that deduplicates, assigns per-batch IDs, builds the summary and top lists, and serializes output.
- **JSON_Validator**: The component that verifies the assembled output is strict valid JSON with the required top-level keys.
- **Processing_Endpoint**: The invocable entry point (e.g., an HTTP endpoint or batch-job command) through which a caller submits a batch and configuration and receives the strict JSON output.
- **Hosting_Environment**: The deployment target that runs the Agent as a service component (e.g., Render), supplied with build and runtime configuration from the source repository.
- **SourceItem**: An input record with required `source_name`, `source_type`, and `raw_text` fields, plus optional structured payloads.
- **source_type**: One of `marketplace`, `broker_directory`, `insolvency_platform`, `chamber_directory`, `social`, `news`.
- **RawFields**: The uniform intermediate record produced by a `Source_Handler`.
- **Company / Deal / Founder / Contact**: The four structured entity types defined in the design data models.
- **ThesisMatch**: The scoring result embedded in each `Deal` (filter outcomes, `overall_score`, `classification`, `explanation`).
- **ThesisConfig**: The injected configuration carrying thresholds, banned/preferred sector sets, and source registry.
- **thesis filter**: One of the five filters — age, sector, financial, founder, AI-automation — each evaluated as a tri-state value.
- **tri-state value**: A value of exactly `true`, `false`, or `null` (unknown).
- **banned_sector_flag**: A Boolean on `Company`, `true` when the business is tobacco, liquor/alcohol-core, or gambling/betting/casino/gaming.
- **excluded sector**: Any sector that sets `banned_sector_flag = true`.
- **preferred sector**: Manufacturing, bookkeeping/accounting, financial/professional services with recurring B2B revenue, and operationally-intensive service firms with AI/automation upside.
- **deal_size_bucket**: One of `small`, `lower_mid`, `core_mid`, `upper_mid`, `unknown`.
- **enterprise value (EV)**: The best-estimate transaction value derived from `asking_price` or description; `null` when not derivable.
- **core EV range**: Enterprise value from approximately USD 10,000,000 to USD 40,000,000.
- **ev_absolute_max**: The absolute maximum enterprise value (approximately USD 50,000,000) above which a deal is forced to `reject`.
- **clearly too large / oversized**: A deal whose enterprise value clearly exceeds `ev_absolute_max`.
- **ESTIMATED**: A flag marking a numeric value that was derived from a stated range (e.g., midpoint) rather than an exact figure.
- **is_stale**: A Boolean on `Deal`, `true` when the most recent of `listing_date` / `last_seen_at` is older than `recency_cutoff_months` (12 months).
- **unknown_date**: The literal text used for `listing_date` / `last_seen_at` when no date is available.
- **recency_cutoff_months**: The staleness threshold in months (12).
- **classification**: The deal outcome — `core_thesis`, `adjacent_thesis`, or `reject`.
- **overall_score**: An integer in `[0, 100]` produced by the `Scoring_Engine`.
- **top_core_thesis_deals**: The summary list of at most 20 non-stale `core_thesis` deals, ordered by descending score.
- **top_contacts_for_outreach**: The summary list of at most 50 prioritized contacts, each with a `priority_reason`.
- **current_year**: The reference year supplied by `ThesisConfig`.
- **min_trading_years**: The minimum full trading years for the age filter (6).
- **min_founder_tenure_years**: The minimum founder tenure years for the founder filter (20).

## Requirements

### Requirement 1: Batch Ingestion of Pre-Fetched Items

**User Story:** As an investment analyst, I want the agent to ingest a batch of pre-fetched source items, so that opportunities can be processed without any live web access.

#### Acceptance Criteria

1. WHEN a batch is submitted for processing, THE Ingestion_Loader SHALL validate that the batch is a well-formed list of SourceItem records before any downstream stage executes.
2. THE Ingestion_Loader SHALL require that every SourceItem contains a non-empty `source_name`, a `source_type`, and a non-empty `raw_text`.
3. IF a SourceItem is missing `source_name`, `source_type`, or `raw_text`, THEN THE Ingestion_Loader SHALL reject that item and SHALL NOT emit a partial or fabricated deal for it.
4. WHEN one or more SourceItems are rejected during ingestion, THE Ingestion_Loader SHALL continue processing the remaining valid items and SHALL record the count of skipped items.
5. THE Agent SHALL NOT perform any outbound network request or live website fetch during processing.

### Requirement 2: Source-Type Routing and Handlers

**User Story:** As an investment analyst, I want each item routed to a handler matching its source type, so that source-specific conventions are correctly interpreted.

#### Acceptance Criteria

1. WHEN a valid SourceItem is processed, THE Source_Router SHALL dispatch it to the handler associated with its `source_type`.
2. THE Source_Router SHALL support the source types `marketplace`, `broker_directory`, `insolvency_platform`, `chamber_directory`, `social`, and `news`.
3. WHERE a SourceItem originates from the configured paid source `scaling.com.au` or `scalingup.com.au`, THE Source_Router SHALL route the item to the marketplace handler.
4. IF a SourceItem has a `source_type` not present in the supported enum, THEN THE Source_Router SHALL route the item to a generic handler that extracts only safely-identifiable fields and sets all others to `null`.
5. WHEN the marketplace handler processes an item, THE Source_Handler SHALL extract the deal listing fields and any broker contacts present.
6. WHEN the broker_directory handler processes an item, THE Source_Handler SHALL extract broker contacts annotated with their sector and deal-size focus, and SHALL treat deal records as optional.
7. WHEN the insolvency_platform handler processes an item, THE Source_Handler SHALL set `deal_type` to `distress` and SHALL extract practitioner contacts and the distressed entity.
8. WHEN the chamber_directory handler processes an item, THE Source_Handler SHALL extract the off-market target firm and association-official relationship leads.
9. WHEN the social or news handler processes an item, THE Source_Handler SHALL extract company and deal-signal information and SHALL NOT treat marketing claims as financial evidence.
10. THE Source_Handler SHALL NOT invent values not present in the SourceItem.

### Requirement 3: Normalization and Conservative Inference

**User Story:** As an investment analyst, I want extracted data normalized conservatively, so that the output never contains fabricated figures.

#### Acceptance Criteria

1. WHEN a field cannot be confidently extracted from a SourceItem, THE Normalizer SHALL set that field to `null` (or `"unknown"` for enum-like text).
2. WHEN a numeric financial value is provided as a range, THE Normalizer SHALL derive a single value from the range and SHALL flag that value as `ESTIMATED`.
3. WHEN `founded_year` is present, THE Normalizer SHALL compute `age_years` as `current_year - founded_year`.
4. IF `founded_year` is absent, THEN THE Normalizer SHALL set `age_years` to `null`.
5. WHEN a founder `start_year` is present, THE Normalizer SHALL compute `tenure_years` from `start_year`.
6. IF a founder `start_year` is absent, THEN THE Normalizer SHALL set `tenure_years` to `null`.
7. WHEN a `Deal` has a non-null currency-bearing amount, THE Normalizer SHALL populate the paired `*_currency` field.
8. THE Normalizer SHALL NOT treat unverifiable or marketing-hype claims as financial evidence.

### Requirement 4: Investment Thesis Filters

**User Story:** As an investment analyst, I want the agent to evaluate the documented thesis filters as tri-state values, so that uncertainty is represented honestly rather than guessed.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL evaluate each thesis filter (`passes_age_filter`, `passes_sector_filter`, `passes_financial_filter`, `passes_founder_filter`, `ai_automation_potential_flag`) as exactly one tri-state value of `true`, `false`, or `null`.
2. WHEN `founded_year` is present AND `current_year - founded_year >= min_trading_years` (6), THE Scoring_Engine SHALL set `passes_age_filter` to `true`.
3. IF `founded_year` is present AND `current_year - founded_year < min_trading_years`, THEN THE Scoring_Engine SHALL set `passes_age_filter` to `false`, and IF `founded_year` is absent THEN THE Scoring_Engine SHALL set `passes_age_filter` to `null`.
4. IF `banned_sector_flag` is `true`, THEN THE Scoring_Engine SHALL set `passes_sector_filter` to `false`.
5. WHERE the company sector is a preferred sector, THE Scoring_Engine SHALL set `passes_sector_filter` to `true`.
6. IF the company sector is absent or cannot be classified, THEN THE Scoring_Engine SHALL set `passes_sector_filter` to `null`.
7. WHEN `revenue >= min_revenue_usd` AND `ebitda >= min_ebitda_usd` (each approximately USD 250,000-300,000), THE Scoring_Engine SHALL set `passes_financial_filter` to `true`.
8. WHERE the price range or description implies a healthy mid-market deal within the core EV range with healthy margins, THE Scoring_Engine SHALL set `passes_financial_filter` to `true`.
9. IF `revenue`, `ebitda`, and `asking_price` are all absent, THEN THE Scoring_Engine SHALL set `passes_financial_filter` to `null`.
10. WHEN a founder tenure of at least `min_founder_tenure_years` (20) OR multi-decade relevant sector history is present, THE Scoring_Engine SHALL set `passes_founder_filter` to `true`, and IF no founder tenure information is available THEN THE Scoring_Engine SHALL set `passes_founder_filter` to `null`.
11. THE Scoring_Engine SHALL set `ai_automation_potential_flag` to `true` when recurring manual processes with automation upside are present, to `false` when the business is asset-heavy and low-complexity, and to `null` when undetermined.
12. WHEN evaluating geography, THE Scoring_Engine SHALL treat Australian companies (all states and territories) as the primary target, and SHALL treat a non-Australian company as in-scope only when a clear Australian presence or Australian assets/operations are evidenced.

### Requirement 5: Deal-Size Bucketing

**User Story:** As an investment analyst, I want deals categorized by size, so that opportunities are aligned with the fund's target enterprise value range.

#### Acceptance Criteria

1. THE Normalizer SHALL assign each `Deal` a `deal_size_bucket` of exactly one of `small`, `lower_mid`, `core_mid`, `upper_mid`, or `unknown`.
2. IF no enterprise value can be derived for a `Deal`, THEN THE Normalizer SHALL set `deal_size_bucket` to `unknown`.
3. WHEN the derived enterprise value is within the core EV range (approximately USD 10,000,000 to USD 40,000,000), THE Normalizer SHALL set `deal_size_bucket` to `core_mid`.
4. WHEN the derived enterprise value is below the core EV minimum, THE Normalizer SHALL set `deal_size_bucket` to `lower_mid` or `small` according to magnitude.
5. IF the derived enterprise value clearly exceeds `ev_absolute_max` (approximately USD 50,000,000), THEN THE Classifier SHALL force the deal `classification` to `reject`.

### Requirement 6: Franchise Handling

**User Story:** As an investment analyst, I want well-run franchise operators evaluated fairly, so that strong franchise opportunities are not overlooked.

#### Acceptance Criteria

1. WHEN a SourceItem indicates a franchise opportunity, THE Normalizer SHALL set `is_franchise` to `true` and SHALL set `deal_type` to `franchise`.
2. WHERE a franchise operator demonstrates a competitive moat relative to large brands or serves an underserved area, THE Scoring_Engine SHALL evaluate it as an includable stable operator.
3. WHEN franchise unit-economics information is present in the SourceItem, THE Normalizer SHALL capture it in the deal's competitive or business-model notes.

### Requirement 7: Recency and Staleness

**User Story:** As an investment analyst, I want recent opportunities prioritized and stale ones flagged, so that outreach focuses on currently available deals.

#### Acceptance Criteria

1. THE Normalizer SHALL record each deal's `listing_date` and `last_seen_at` when present in the SourceItem.
2. IF both `listing_date` and `last_seen_at` are absent, THEN THE Normalizer SHALL set both fields to `"unknown_date"` and SHALL set `is_stale` to `false`.
3. WHEN the most recent of `listing_date` and `last_seen_at` is older than `recency_cutoff_months` (12), THE Normalizer SHALL set `is_stale` to `true`.
4. WHEN the most recent of `listing_date` and `last_seen_at` is within `recency_cutoff_months`, THE Normalizer SHALL set `is_stale` to `false`.
5. THE Output_Assembler SHALL exclude every deal with `is_stale = true` from `top_core_thesis_deals`.

### Requirement 8: Scoring

**User Story:** As an investment analyst, I want a transparent additive score with conservative penalties, so that deal strength is quantified consistently.

#### Acceptance Criteria

1. WHEN computing a deal score, THE Scoring_Engine SHALL start from a base of `0`.
2. WHEN `passes_sector_filter` is `true`, THE Scoring_Engine SHALL add `25` points.
3. WHEN `passes_age_filter` is `true`, THE Scoring_Engine SHALL add `20` points.
4. WHEN `passes_financial_filter` is `true`, THE Scoring_Engine SHALL add `20` points.
5. WHEN `passes_founder_filter` is `true`, THE Scoring_Engine SHALL add `15` points.
6. WHEN `ai_automation_potential_flag` is `true`, THE Scoring_Engine SHALL add `10` points.
7. WHEN information is missing or vague, THE Scoring_Engine SHALL subtract a data-quality penalty of at most `20` points.
8. THE Scoring_Engine SHALL clamp the final `overall_score` to the inclusive range `[0, 100]`.
9. THE Scoring_Engine SHALL add positive points only for filters evaluated as `true`, and SHALL add no points for filters evaluated as `false` or `null`.

### Requirement 9: Classification and Explanation

**User Story:** As an investment analyst, I want each deal classified with a clear rationale, so that I can quickly understand why a deal is core, adjacent, or rejected.

#### Acceptance Criteria

1. THE Classifier SHALL assign each `Deal` exactly one `classification` of `core_thesis`, `adjacent_thesis`, or `reject`.
2. IF the deal is in an excluded sector (`passes_sector_filter = false`), THEN THE Classifier SHALL set `classification` to `reject`.
3. IF the deal is clearly too large (enterprise value exceeds `ev_absolute_max`), THEN THE Classifier SHALL set `classification` to `reject`.
4. IF `overall_score < 40`, THEN THE Classifier SHALL set `classification` to `reject`.
5. WHEN `overall_score >= 70` AND no exclusion flag is present, THE Classifier SHALL set `classification` to `core_thesis`.
6. WHEN `40 <= overall_score < 70` AND no reject condition applies, THE Classifier SHALL set `classification` to `adjacent_thesis`.
7. WHERE exactly one key thesis filter is `null` while the others are strong AND no reject condition applies, THE Classifier SHALL set `classification` to `adjacent_thesis`.
8. THE Classifier SHALL produce a concise one-paragraph `explanation` for each deal that cites the specific thesis filters and exclusion conditions driving the classification.

### Requirement 10: Entity Extraction

**User Story:** As an investment analyst, I want the agent to build structured Company, Deal, Founder, and Contact entities, so that the downstream CRM is populated with consistent records.

#### Acceptance Criteria

1. WHEN processing a SourceItem, THE Normalizer SHALL build `Company`, `Deal`, `Founder`, and `Contact` entities according to the data models defined in the design document.
2. THE Normalizer SHALL populate each `Company` with a non-empty `name` and `country`, and SHALL set `age_years` only when `founded_year` is present.
3. THE Normalizer SHALL embed a `ThesisMatch` in every `Deal`, containing the tri-state filter outcomes, `overall_score`, `classification`, and `explanation`.
4. THE Normalizer SHALL populate each `Founder` with a non-empty `name` and `role`, and SHALL set `tenure_years` only when `start_year` is present.
5. THE Output_Assembler SHALL assign unique per-batch identifiers using the patterns `deal_NNN`, `company_NNN`, `founder_NNN`, and `contact_NNN`.

### Requirement 11: Contact and Relationship Lead Extraction

**User Story:** As a deal originator, I want relationship leads extracted and annotated, so that I can prioritize outreach to the most relevant intermediaries.

#### Acceptance Criteria

1. WHEN processing a SourceItem, THE Contact_Extractor SHALL build `Contact` records for brokers, liquidators, bankers, founders, and association officials present in the source.
2. THE Contact_Extractor SHALL populate each `Contact` with `notes_on_relevance_to_deals` describing the deal types, sectors, and sizes the contact handles, when that information is derivable.
3. WHEN a contact is included in `top_contacts_for_outreach`, THE Contact_Extractor SHALL populate that contact's `priority_reason`.
4. THE Contact_Extractor SHALL set `priority_reason` only for contacts surfaced in the outreach list.

### Requirement 12: Strict JSON Output Contract

**User Story:** As a downstream ETL engineer, I want a single strict JSON output, so that the result can be parsed directly without prose contamination.

#### Acceptance Criteria

1. THE Output_Assembler SHALL emit a single JSON object with exactly the top-level keys `deals`, `companies`, `founders`, `contacts`, and `summary`, and SHALL NOT include any surrounding prose or markdown fences.
2. THE Output_Assembler SHALL assign within each batch a unique identifier to every deal, company, founder, and contact.
3. THE Output_Assembler SHALL ensure every `Deal` carries a non-null `source_name` and a non-null `external_listing_id_or_url`.
4. THE Output_Assembler SHALL ensure every `Contact` carries a non-null `source_name` and a non-null `source_type`.
5. THE Output_Assembler SHALL build a `summary` containing `core_thesis_deal_count`, `adjacent_thesis_deal_count`, and `reject_count`.
6. THE Output_Assembler SHALL build `top_core_thesis_deals` containing at most 20 entries, all non-stale and all classified `core_thesis`, ordered by descending `overall_score`.
7. THE Output_Assembler SHALL build `top_contacts_for_outreach` containing at most 50 entries, each carrying a non-null `priority_reason`.
8. THE Output_Assembler SHALL ensure the sum of `core_thesis_deal_count`, `adjacent_thesis_deal_count`, and `reject_count` equals the number of deals in `deals`.
9. THE JSON_Validator SHALL verify that the assembled output is strict valid JSON with the required top-level keys before it is returned.
10. THE Output_Assembler SHALL represent missing data as `null` (or `"unknown"` / `"unknown_date"` for enum/date text) and SHALL NOT represent it with invented values.

### Requirement 13: Behavior and Risk Rules

**User Story:** As an investment committee member, I want the agent to behave conservatively and enforce hard rules, so that the output is trustworthy and compliant.

#### Acceptance Criteria

1. THE Agent SHALL prefer `null` / `"unknown"` / `"unknown_date"` over any fabricated value across all entities.
2. IF a deal's company is in an excluded sector, THEN THE Agent SHALL force the deal to `reject` regardless of any other strengths.
3. IF a deal is clearly too large, THEN THE Agent SHALL force the deal to `reject` regardless of any other strengths.
4. WHEN financial signals are conflicting or appear to be marketing hype, THE Agent SHALL treat the unverifiable claims as absent and apply the data-quality penalty.
5. THE Agent SHALL produce deal explanations that are specific and cite the filters and conditions that determined the classification.
6. WHEN given identical input batch and configuration, THE Agent SHALL produce identical output (deterministic processing).

### Requirement 14: Correctness Properties (Property-Based Testable Invariants)

**User Story:** As a quality engineer, I want the documented correctness properties expressed as verifiable invariants, so that they can be validated with property-based testing across many generated batches.

#### Acceptance Criteria

1. FOR ALL deals in the output, THE Scoring_Engine SHALL ensure `0 <= overall_score <= 100`. (P1)
2. FOR ALL deals whose company has `banned_sector_flag = true`, THE Classifier SHALL ensure `classification = reject`. (P2)
3. FOR ALL deals that are clearly too large, THE Classifier SHALL ensure `classification = reject`. (P3)
4. FOR ALL deals with `overall_score < 40`, THE Classifier SHALL ensure `classification = reject`. (P4)
5. FOR ALL deals with `classification = core_thesis`, THE Classifier SHALL ensure `overall_score >= 70` AND no exclusion flag is present. (P5)
6. FOR ALL deals, THE Output_Assembler SHALL ensure `source_name` and `external_listing_id_or_url` are non-null, AND FOR ALL contacts, `source_name` and `source_type` are non-null. (P6)
7. THE Output_Assembler SHALL ensure all `deal_id`, `company_id`, `person_id`, and `contact_id` values are distinct within the batch. (P7)
8. THE Output_Assembler SHALL ensure `top_core_thesis_deals` has at most 20 entries and that every entry is non-stale and classified `core_thesis`. (P8)
9. THE Output_Assembler SHALL ensure `top_core_thesis_deals` is ordered by descending `overall_score`. (P9)
10. THE Output_Assembler SHALL ensure `top_contacts_for_outreach` has at most 50 entries and that every entry has a non-null `priority_reason`. (P10)
11. THE Output_Assembler SHALL ensure `core_thesis_deal_count + adjacent_thesis_deal_count + reject_count` equals the number of deals. (P11)
12. FOR ALL deals whose financial value was derived from a range, THE Normalizer SHALL flag that value as `ESTIMATED`. (P12)
13. FOR ALL deals, THE Scoring_Engine SHALL ensure every thesis filter field is one of `true`, `false`, or `null`. (P13)
14. FOR ALL filter sets where one has at least as many `true` flags as another at the same positions and the penalty is held constant, THE Scoring_Engine SHALL ensure the score is monotonic (does not decrease). (P14)
15. WHEN invoked twice with identical input, THE Agent SHALL produce identical output. (P15)
16. FOR ALL deals with `is_stale = true`, THE Output_Assembler SHALL exclude the deal from `top_core_thesis_deals`. (P16)
17. THE JSON_Validator SHALL ensure the output is strict valid JSON whose top-level keys are exactly `deals`, `companies`, `founders`, `contacts`, and `summary`. (P17)

### Requirement 15: Deployable Processing Service

**User Story:** As a platform engineer, I want the agent packaged as a deployable, invocable service component, so that it can be hosted (e.g., on Render) and called as part of the TransformBiz pipeline rather than only run as local logic.

#### Acceptance Criteria

1. THE Agent SHALL be packaged as a deployable service component exposing a Processing_Endpoint that accepts a batch and a configuration and returns the strict JSON output contract.
2. WHEN the Processing_Endpoint receives a request containing a well-formed batch and configuration, THE Agent SHALL execute the full processing pipeline and return the strict JSON output described in Requirement 12.
3. IF the Processing_Endpoint receives a malformed request (missing or non-list batch, or absent configuration), THEN THE Agent SHALL return a descriptive error response and SHALL NOT emit a partial or fabricated deal output.
4. WHERE the Agent runs in a Hosting_Environment, THE Agent SHALL obtain its `ThesisConfig` and source registry (including the configured `scaling.com.au` / `scalingup.com.au` marketplace source) from injected configuration rather than from hard-coded values.
5. THE source repository SHALL include the build, dependency, and start-command definitions required to deploy and run the Agent in the Hosting_Environment.
6. WHILE the Processing_Endpoint is handling a request, THE Agent SHALL NOT perform any outbound network request or live website fetch beyond returning the computed output.
