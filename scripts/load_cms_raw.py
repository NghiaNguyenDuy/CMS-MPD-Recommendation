"""
Medicare Part D ETL Script - SPUF Data Processing

This module extracts, transforms, and loads Medicare Part D Prescription Drug Plan data
from CMS SPUF (Summary PUF) files into parquet format for efficient querying.

Data Sources:
- SPUF 2025 Q3 Plan Information, Formulary, Cost, Network, and Pricing files
- Source: https://www.cms.gov/data-research/statistics-trends-and-reports/
         medicare-advantagepart-d-contract-and-enrollment-data/

Purpose:
This ETL pipeline processes 9 key SPUF tables that form the backbone of Medicare Part D
plan recommendation system:
1. Plan Information - Plan metadata, premiums, deductibles, service areas
2. Geographic Locator - County to region mapping for MA-PD and PDP plans
3. Basic Drugs Formulary - Drug coverage by formulary with tiers and restrictions
4. Excluded Drugs - Explicitly excluded or conditionally covered drugs
5. Indication Based Coverage (IBC) - Disease-specific coverage constraints
6. Beneficiary Cost - Cost-sharing rules by tier, coverage phase, and pharmacy type
7. Insulin Beneficiary Cost - Special insulin copays (IRA $35 cap compliance)
8. Pharmacy Networks - Preferred vs standard pharmacy status and dispensing fees
9. Pricing File - Unit costs by NDC and days supply for retail pharmacies

Output:
All tables saved as parquet files to data/SPUF/ for efficient downstream processing.

Medicare Part D Key Concepts:
- MA-PD: Medicare Advantage Prescription Drug plans (local, county-based)
- PDP: Stand-alone Prescription Drug Plans (regional)
- Formulary: List of covered drugs organized by tiers
- Tiers: 1-2 Generic, 3-4 Brand, 5+ Specialty
- Restrictions: PA (Prior Auth), ST (Step Therapy), QL (Quantity Limits)
- IRA Insulin Cap: $35/month maximum copay for insulin (started 2023)
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Data source directory (CMS SPUF files)
DATA_PATH = './datasets/SPUF_2025_20251009/'

# Output directory for processed parquet files
OUTPUT_PATH = './data/SPUF/'

# Chunk size for processing large files (100K rows at a time)
CHUNK_SIZE = 100000

# Plan Information Schema Definition
# This defines the expected data types for all plan-level fields
PLAN_INFO_SCHEMA = {
    'CONTRACT_ID': str,      # Unique contract identifier (e.g., H1234, S5678)
    'PLAN_ID': str,          # Plan identifier within contract (e.g., 001, 002)
    'SEGMENT_ID': str,       # Segment for cost variations (usually '000' for PDPs)
    'CONTRACT_NAME': str,    # Marketing name of the organization
    'PLAN_NAME': str,        # Marketing name of the specific plan
    'FORMULARY_ID': str,     # Link to formulary table (drug coverage list)
    'PREMIUM': float,        # Monthly premium in dollars
    'DEDUCTIBLE': float,     # Annual deductible in dollars
    'MA_REGION_CODE': str,   # Medicare Advantage region (for MA-PD plans)
    'PDP_REGION_CODE': str,  # PDP region code (34 regions nationwide)
    'STATE': str,            # State FIPS code (for MA-PD local plans)
    'COUNTY_CODE': str,      # 5-digit SSA county code (SSCCC format)
    'SNP': int,              # Special Needs Plan indicator (0=No, 1+=Yes)
    'PLAN_SUPPRESSED_YN': str  # Whether plan data is suppressed (Y/N)
}

def read_plan_information(file_path):
    """
    Load and process Medicare Part D plan information.
    
    This function reads the Plan Information SPUF file which contains core metadata
    about all Medicare Advantage Prescription Drug (MA-PD) and stand-alone Prescription
    Drug Plans (PDPs) offered in the Medicare program.
    
    Medicare Plan Types:
    - MA-PD (H-contracts, R-contracts): Combined health + drug coverage, county-based
    - PDP (S-contracts): Drug coverage only, regional (34 PDP regions)
    
    Key Plan Attributes:
    - Premium: Monthly cost to enroll (can be $0 for some plans)
    - Deductible: Amount beneficiary pays before plan coverage starts (can be $0)
    - Formulary: Linked list of covered drugs (separate table)
    - Service Area: Geographic availability (county for MA-PD, region for PDP)
    
    Args:
        file_path (str): Path to plan information pipe-delimited text file
    
    Returns:
        pd.DataFrame: Processed plan information with additional derived fields:
            - PLAN_KEY: Composite key (CONTRACT_ID + PLAN_ID + SEGMENT_ID)
            - PLAN_TYPE: First letter of CONTRACT_ID (H/R/S)
            - IS_MA_PD: Boolean flag for MA-PD plans
            - IS_PDP: Boolean flag for stand-alone PDPs
            - PLAN_SUPPRESSED: Boolean conversion of suppressed flag
    
    Business Rules Applied:
    1. Create composite PLAN_KEY for unique identification across all tables
    2. Identify plan type from CONTRACT_ID prefix (H/R = MA-PD, S = PDP)
    3. Ensure premiums and deductibles are non-negative
    4. Convert region codes to numeric for filtering
    5. Standardize text fields (trim whitespace, uppercase)
    """
    # Read pipe-delimited file with proper schema enforcement
    # latin1 encoding handles special characters in plan names
    df = pd.read_csv(
        file_path,
        dtype=PLAN_INFO_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],  # Treat these as missing values
        keep_default_na=True,
        encoding='latin1',
        delimiter='|'
    )
    
    # ===== Data Cleaning and Standardization =====
    
    # Standardize CONTRACT_ID and PLAN_ID (trim whitespace, uppercase)
    # These are used as join keys throughout the system
    df['CONTRACT_ID'] = df['CONTRACT_ID'].str.strip().str.upper()
    df['PLAN_ID'] = df['PLAN_ID'].str.strip()
    
    # SEGMENT_ID defaults to '000' for non-segmented plans (most PDPs)
    # Segmentation allows cost variations within same plan
    df['SEGMENT_ID'] = df['SEGMENT_ID'].str.strip().fillna('000')
    
    # ===== Create Composite Key =====
    # PLAN_KEY uniquely identifies a plan across all SPUF tables
    # Format: {CONTRACT_ID}{PLAN_ID}{SEGMENT_ID} (no separators for compactness)
    # Example: H1234001000, S5678002000
    df['PLAN_KEY'] = df['CONTRACT_ID'] + df['PLAN_ID'] + df['SEGMENT_ID']
    
    # ===== Derive Plan Type =====
    # Medicare plan type is encoded in the first character of CONTRACT_ID:
    # H = Medicare Advantage HMO/PPO with drug coverage (local, county-based)
    # R = Medicare Advantage PFFS/other with drug coverage (regional)
    # S = Stand-alone Prescription Drug Plan (regional, 34 PDP regions)
    df['PLAN_TYPE'] = df['CONTRACT_ID'].str[0]
    
    # Create boolean flags for easier filtering downstream
    df['IS_MA_PD'] = df['PLAN_TYPE'].isin(['H', 'R'])  # Has health coverage component
    df['IS_PDP'] = df['PLAN_TYPE'] == 'S'              # Drug coverage only
    
    # ===== Financial Field Validation =====
    # Ensure premiums and deductibles are non-negative (data quality check)
    # Some plans have $0 premium (subsidized) or $0 deductible - these are valid
    df['PREMIUM'] = df['PREMIUM'].clip(lower=0)
    df['DEDUCTIBLE'] = df['DEDUCTIBLE'].clip(lower=0)
    
    # ===== Region Code Processing =====
    # Convert region codes to numeric for efficient filtering
    # MA_REGION_CODE: Medicare Advantage service area regions
    # PDP_REGION_CODE: 1-34 for nationwide PDP regions
    df['MA_REGION_CODE'] = pd.to_numeric(df['MA_REGION_CODE'], errors='coerce')
    df['PDP_REGION_CODE'] = pd.to_numeric(df['PDP_REGION_CODE'], errors='coerce')
    
    # ===== Boolean Flag Conversion =====
    # Convert Y/N indicator to boolean for easier conditional logic
    df['PLAN_SUPPRESSED'] = df['PLAN_SUPPRESSED_YN'] == 'Y'
    
    # ===== Summary Statistics =====
    print(f"✓ Loaded {len(df):,} plans")
    print(f"  - MA-PD plans: {df['IS_MA_PD'].sum():,}")
    print(f"  - Stand-alone PDPs: {df['IS_PDP'].sum():,}")
    print(f"  - Special Needs Plans: {(df['SNP'] > 0).sum():,}")
    
    return df


# Execute ETL: Load plan information from SPUF file
# This reads the quarterly plan information file and processes it
plan_info = read_plan_information(f'{DATA_PATH}/plan information  PPUF_2025Q3.txt')


BASIC_FORMULARY_SCHEMA = {
    'FORMULARY_ID': str,
    'FORMULARY_VERSION': str,
    'CONTRACT_YEAR': str,
    'RXCUI': str,
    'NDC': str,
    'TIER_LEVEL_VALUE': float,
    'QUANTITY_LIMIT_YN': str,
    'QUANTITY_LIMIT_AMOUNT': str,  # Can be numeric or blank
    'QUANTITY_LIMIT_DAYS': str,    # Can be numeric or blank
    'PRIOR_AUTHORIZATION_YN': str,
    'STEP_THERAPY_YN': str
}

def read_basic_formulary(file_path, chunksize=CHUNK_SIZE):
    """
    Read BASIC_DRUGS_FORMULARY_FILE (can be very large - use chunks)
    """
    chunks = []
    
    for chunk in pd.read_csv(
        file_path,
        dtype=BASIC_FORMULARY_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        delimiter='|',
        chunksize=chunksize
    ):
        # Clean drug identifiers
        chunk['RXCUI'] = chunk['RXCUI'].str.strip()
        chunk['NDC'] = chunk['NDC'].str.strip()
        chunk['FORMULARY_ID'] = chunk['FORMULARY_ID'].str.strip()
        
        # Create composite key
        chunk['FORM_DRUG_KEY'] = chunk['FORMULARY_ID'] + '_' + chunk['NDC']
        
        # Parse quantity limits
        chunk['QUANTITY_LIMIT_AMOUNT'] = pd.to_numeric(
            chunk['QUANTITY_LIMIT_AMOUNT'], errors='coerce'
        )
        chunk['QUANTITY_LIMIT_DAYS'] = pd.to_numeric(
            chunk['QUANTITY_LIMIT_DAYS'], errors='coerce'
        )
        
        # Boolean flags for restrictions
        chunk['HAS_QUANTITY_LIMIT'] = chunk['QUANTITY_LIMIT_YN'] == 'Y'
        chunk['HAS_PRIOR_AUTH'] = chunk['PRIOR_AUTHORIZATION_YN'] == 'Y'
        chunk['HAS_STEP_THERAPY'] = chunk['STEP_THERAPY_YN'] == 'Y'
        
        # Count total restrictions
        chunk['RESTRICTION_COUNT'] = (
            chunk['HAS_QUANTITY_LIMIT'].astype(int) +
            chunk['HAS_PRIOR_AUTH'].astype(int) +
            chunk['HAS_STEP_THERAPY'].astype(int)
        )
        
        # Tier categorization
        chunk['IS_GENERIC_TIER'] = chunk['TIER_LEVEL_VALUE'] <= 2
        chunk['IS_BRAND_TIER'] = (chunk['TIER_LEVEL_VALUE'] >= 3) & (chunk['TIER_LEVEL_VALUE'] < 5)
        chunk['IS_SPECIALTY_TIER'] = chunk['TIER_LEVEL_VALUE'] >= 5
        
        chunks.append(chunk)
    
    df = pd.concat(chunks, ignore_index=True)
    
    print(f"✓ Loaded {len(df):,} formulary entries")
    print(f"  - Unique formularies: {df['FORMULARY_ID'].nunique():,}")
    print(f"  - Unique drugs (RXCUI): {df['RXCUI'].nunique():,}")
    print(f"  - Unique NDCs: {df['NDC'].nunique():,}")
    print(f"  - With restrictions: {(df['RESTRICTION_COUNT'] > 0).sum():,} ({(df['RESTRICTION_COUNT'] > 0).mean()*100:.1f}%)")
    
    return df

# Usage
basic_formulary = read_basic_formulary(f'{DATA_PATH}basic drugs formulary file  PPUF_2025Q3.txt')


EXCLUDED_DRUGS_SCHEMA = {
    'CONTRACT_ID': str,
    'PLAN_ID': str,
    'RXCUI': str,
    'TIER': float,  # Can be blank/null if not covered at all
    'QUANTITY_LIMIT_YN': str,  # NOTE: Uses 0/1 instead of N/Y
    'QUANTITY_LIMIT_AMOUNT': str,
    'QUANTITY_LIMIT_DAYS': str,
    'PRIOR_AUTH_YN': str,
    'STEP_THERAPY_YN': str,
    'CAPPED_BENEFIT_YN': str
}

def read_excluded_drugs(file_path):
    """
    Read EXCLUDED_DRUGS_FORMULARY_FILE
    """
    df = pd.read_csv(
        file_path,
        dtype=EXCLUDED_DRUGS_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        delimiter='|'
    )
    
    # Clean identifiers
    df['CONTRACT_ID'] = df['CONTRACT_ID'].str.strip()
    df['PLAN_ID'] = df['PLAN_ID'].str.strip()
    df['RXCUI'] = df['RXCUI'].str.strip()
    
    # Create plan key
    df['PLAN_KEY'] = df['CONTRACT_ID'] + df['PLAN_ID'] + '000'  # Excluded drugs don't use segment
    
    # Handle different Y/N encoding (uses 0/1 for quantity limit!)
    df['HAS_QUANTITY_LIMIT'] = df['QUANTITY_LIMIT_YN'] == '1'
    df['HAS_PRIOR_AUTH'] = df['PRIOR_AUTH_YN'] == 'Y'
    df['HAS_STEP_THERAPY'] = df['STEP_THERAPY_YN'] == 'Y'
    df['HAS_CAPPED_BENEFIT'] = df['CAPPED_BENEFIT_YN'] == 'Y'
    
    # Flag for completely excluded vs conditionally covered
    df['COMPLETELY_EXCLUDED'] = df['TIER'].isna()
    df['CONDITIONALLY_COVERED'] = ~df['COMPLETELY_EXCLUDED']
    
    print(f"✓ Loaded {len(df):,} excluded drug entries")
    print(f"  - Completely excluded: {df['COMPLETELY_EXCLUDED'].sum():,}")
    print(f"  - Conditionally covered: {df['CONDITIONALLY_COVERED'].sum():,}")
    
    return df

# Usage
excluded_drugs = read_excluded_drugs(f'{DATA_PATH}excluded drugs formulary file  PPUF_2025Q3.txt')


INDICATION_COVERAGE_SCHEMA = {
    'CONTRACT_ID': str,
    'PLAN_ID': str,
    'RXCUI': str,
    'DISEASE': str
}

def read_indication_coverage(file_path):
    """
    Read INDICATION_BASED_COVERAGE_FORMULARY_FILE
    """
    df = pd.read_csv(
        file_path,
        dtype=INDICATION_COVERAGE_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        delimiter='|'
    )
    
    # Clean identifiers
    df['CONTRACT_ID'] = df['CONTRACT_ID'].str.strip()
    df['PLAN_ID'] = df['PLAN_ID'].str.strip()
    df['RXCUI'] = df['RXCUI'].str.strip()
    df['DISEASE'] = df['DISEASE'].str.strip()
    
    # Create keys
    df['PLAN_KEY'] = df['CONTRACT_ID'] + df['PLAN_ID'] + '000'
    df['INDICATION_KEY'] = df['PLAN_KEY'] + '_' + df['RXCUI'] + '_' + df['DISEASE']
    
    # Count indications per drug per plan
    df['INDICATIONS_PER_DRUG'] = df.groupby(['PLAN_KEY', 'RXCUI'])['DISEASE'].transform('count')
    
    print(f"✓ Loaded {len(df):,} indication-based coverage rules")
    print(f"  - Unique drugs with indication restrictions: {df['RXCUI'].nunique():,}")
    print(f"  - Unique indications: {df['DISEASE'].nunique():,}")
    
    return df

# Usage
indication_coverage = read_indication_coverage(f'{DATA_PATH}Indication Based Coverage Formulary File  PPUF_2025Q3.txt')


BENEFICIARY_COST_SCHEMA = {
    'CONTRACT_ID': str,
    'PLAN_ID': str,
    'SEGMENT_ID': str,
    'COVERAGE_LEVEL': int,
    'TIER': float,
    'DAYS_SUPPLY': int,
    
    # Preferred retail
    'COST_TYPE_PREF': int,
    'COST_AMT_PREF': float,
    'COST_MIN_AMT_PREF': str,  # Can be blank
    'COST_MAX_AMT_PREF': float,
    
    # Non-preferred retail
    'COST_TYPE_NONPREF': int,
    'COST_AMT_NONPREF': float,
    'COST_MIN_AMT_NONPREF': str,
    'COST_MAX_AMT_NONPREF': float,
    
    # Preferred mail
    'COST_TYPE_MAIL_PREF': int,
    'COST_AMT_MAIL_PREF': float,
    'COST_MIN_AMT_MAIL_PREF': str,
    'COST_MAX_AMT_MAIL_PREF': float,
    
    # Non-preferred mail
    'COST_TYPE_MAIL_NONPREF': int,
    'COST_AMT_MAIL_NONPREF': float,
    'COST_MIN_AMT_MAIL_NONPREF': str,
    'COST_MAX_AMT_MAIL_NONPREF': float,
    
    # Flags
    'TIER_SPECIALTY_YN': str,
    'DED_APPLIES_YN': str
}

def read_beneficiary_cost(file_path, chunksize=CHUNK_SIZE):
    """
    Read BENEFICIARY_COST_FILE (large file - use chunks)
    """
    chunks = []
    
    for chunk in pd.read_csv(
        file_path,
        dtype=BENEFICIARY_COST_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        chunksize=chunksize,
        delimiter='|'
    ):
        # Clean identifiers
        chunk['CONTRACT_ID'] = chunk['CONTRACT_ID'].str.strip()
        chunk['PLAN_ID'] = chunk['PLAN_ID'].str.strip()
        chunk['SEGMENT_ID'] = chunk['SEGMENT_ID'].str.strip().fillna('000')
        
        # Create composite key
        chunk['COST_KEY'] = (
            chunk['CONTRACT_ID'] + chunk['PLAN_ID'] + chunk['SEGMENT_ID'] +
            '_T' + chunk['TIER'].astype(str) +
            '_C' + chunk['COVERAGE_LEVEL'].astype(str) +
            '_D' + chunk['DAYS_SUPPLY'].astype(str)
        )
        
        # Parse MIN_AMT fields (character fields with possible blanks)
        for ptype in ['PREF', 'NONPREF', 'MAIL_PREF', 'MAIL_NONPREF']:
            min_col = f'COST_MIN_AMT_{ptype}'
            chunk[min_col] = pd.to_numeric(chunk[min_col], errors='coerce')
        
        # Boolean flags
        chunk['IS_SPECIALTY_TIER'] = chunk['TIER_SPECIALTY_YN'] == 'Y'
        chunk['DEDUCTIBLE_APPLIES'] = chunk['DED_APPLIES_YN'] == 'Y'
        
        # Days supply mapping
        chunk['DAYS_SUPPLY_LABEL'] = chunk['DAYS_SUPPLY'].map({
            1: '30_days',
            2: '90_days',
            3: 'other',
            4: '60_days'
        })
        
        # Coverage level mapping
        chunk['COVERAGE_LEVEL_LABEL'] = chunk['COVERAGE_LEVEL'].map({
            0: 'pre_deductible',
            1: 'initial_coverage',
            3: 'catastrophic'
        })
        
        # Cost type labels
        cost_type_map = {0: 'not_offered', 1: 'copay', 2: 'coinsurance'}
        for ptype in ['PREF', 'NONPREF', 'MAIL_PREF', 'MAIL_NONPREF']:
            type_col = f'COST_TYPE_{ptype}'
            label_col = f'COST_TYPE_{ptype}_LABEL'
            chunk[label_col] = chunk[type_col].map(cost_type_map)
        
        # Calculate minimum cost across all pharmacy types
        cost_cols = [f'COST_AMT_{pt}' for pt in ['PREF', 'NONPREF', 'MAIL_PREF', 'MAIL_NONPREF']]
        chunk['MIN_COST'] = chunk[cost_cols].min(axis=1)
        chunk['MAX_COST'] = chunk[cost_cols].max(axis=1)
        
        # Identify best pharmacy type
        chunk['BEST_PHARMACY_TYPE'] = chunk[cost_cols].idxmin(axis=1).str.replace('COST_AMT_', '')
        
        chunks.append(chunk)
    
    df = pd.concat(chunks, ignore_index=True)
    
    print(f"✓ Loaded {len(df):,} cost-sharing records")
    print(f"  - Coverage levels: {df['COVERAGE_LEVEL'].unique()}")
    print(f"  - Tier range: {df['TIER'].min():.1f} - {df['TIER'].max():.1f}")
    print(f"  - Specialty tiers: {df['IS_SPECIALTY_TIER'].sum():,}")
    print(f"  - With deductible: {df['DEDUCTIBLE_APPLIES'].sum():,} ({df['DEDUCTIBLE_APPLIES'].mean()*100:.1f}%)")
    
    return df

# Usage
beneficiary_cost = read_beneficiary_cost(f'{DATA_PATH}beneficiary cost file  PPUF_2025Q3.txt')


INSULIN_COST_SCHEMA = {
    'CONTRACT_ID': str,
    'PLAN_ID': str,
    'SEGMENT_ID': str,
    'TIER': str,  # Can be missing for defined standard plans
    'DAYS_SUPPLY': int,
    'COPAY_AMT_PREF_INSLN': float,
    'COPAY_AMT_NONPREF_INSLN': float,
    'COPAY_AMT_MAIL_PREF_INSLN': float,
    'COPAY_AMT_MAIL_NONPREF_INSLN': float
}

def read_insulin_cost(file_path):
    """
    Read INSULIN_BENEFICIARY_COST_FILE
    """
    df = pd.read_csv(
        file_path,
        dtype=INSULIN_COST_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        delimiter='|'
    )
    
    # Clean identifiers
    df['CONTRACT_ID'] = df['CONTRACT_ID'].str.strip()
    df['PLAN_ID'] = df['PLAN_ID'].str.strip()
    df['SEGMENT_ID'] = df['SEGMENT_ID'].str.strip().fillna('000')
    
    # Create key
    df['INSULIN_COST_KEY'] = (
        df['CONTRACT_ID'] + df['PLAN_ID'] + df['SEGMENT_ID'] +
        '_T' + df['TIER'].fillna(0).astype(str) +
        '_D' + df['DAYS_SUPPLY'].astype(str)
    )
    
    # Days supply mapping
    df['DAYS_SUPPLY_LABEL'] = df['DAYS_SUPPLY'].map({
        1: '30_days',
        2: '90_days',
        3: 'other',
        4: '60_days'
    })
    
    # Calculate minimum insulin cost
    copay_cols = [
        'copay_amt_pref_insln',
        'copay_amt_nonpref_insln',
        'copay_amt_mail_pref_insln',
        'copay_amt_mail_nonpref_insln'
    ]
    for col in copay_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['MIN_INSULIN_COPAY'] = df[copay_cols].min(axis=1)
    df['MAX_INSULIN_COPAY'] = df[copay_cols].max(axis=1)
    
    # Verify $35 cap (should not exceed $35 for 30-day, $105 for 90-day)
    df['EXCEEDS_CAP'] = (
        ((df['DAYS_SUPPLY'] == 1) & (df['MIN_INSULIN_COPAY'] > 35)) |
        ((df['DAYS_SUPPLY'] == 2) & (df['MIN_INSULIN_COPAY'] > 105))
    )
    
    print(f"✓ Loaded {len(df):,} insulin cost records")
    print(f"  - Plans with insulin coverage: {df['CONTRACT_ID'].nunique():,}")
    print(f"  - Records exceeding IRA cap: {df['EXCEEDS_CAP'].sum():,}")
    
    return df

# Usage
insulin_cost = read_insulin_cost(f'{DATA_PATH}insulin beneficiary cost file  PPUF_2025Q3.txt')


PRICING_SCHEMA = {
    'CONTRACT_ID': str,
    'PLAN_ID': str,
    'SEGMENT_ID': str,
    'NDC': str,
    'DAYS_SUPPLY': int,
    'UNIT_COST': float
}

def read_pricing(file_path, chunksize=CHUNK_SIZE):
    """
    Read PRICING_FILE (very large - use chunks)
    """
    chunks = []
    
    for chunk in pd.read_csv(
        file_path,
        dtype=PRICING_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        chunksize=chunksize,
        delimiter='|'
    ):
        # Clean identifiers
        chunk['CONTRACT_ID'] = chunk['CONTRACT_ID'].str.strip()
        chunk['PLAN_ID'] = chunk['PLAN_ID'].str.strip()
        chunk['SEGMENT_ID'] = chunk['SEGMENT_ID'].str.strip().fillna('000')
        chunk['NDC'] = chunk['NDC'].str.strip()
        
        # Create keys
        chunk['PLAN_KEY'] = chunk['CONTRACT_ID'] + chunk['PLAN_ID'] + chunk['SEGMENT_ID']
        chunk['PRICING_KEY'] = chunk['PLAN_KEY'] + '_' + chunk['NDC'] + '_' + chunk['DAYS_SUPPLY'].astype(str)
        chunk['DAYS_SUPPLY_CODE'] = chunk['DAYS_SUPPLY'].map({30: 1, 90: 2, 60: 4})
        # Validate unit cost (should be positive)
        chunk['UNIT_COST'] = chunk['UNIT_COST'].clip(lower=0)
        
        # Log transform for modeling
        chunk['LOG_UNIT_COST'] = np.log1p(chunk['UNIT_COST'])
        
        # Cost categorization
        chunk['COST_CATEGORY'] = pd.cut(
            chunk['UNIT_COST'],
            bins=[0, 0.5, 5, 50, 500, np.inf],
            labels=['very_low', 'low', 'medium', 'high', 'very_high']
        )
        
        # Calculate total cost for standard quantities
        if chunk['DAYS_SUPPLY'].iloc[0] == 30:
            chunk['COST_30_UNITS'] = chunk['UNIT_COST'] * 30
        elif chunk['DAYS_SUPPLY'].iloc[0] == 90:
            chunk['COST_90_UNITS'] = chunk['UNIT_COST'] * 90
        
        chunks.append(chunk)
    
    df = pd.concat(chunks, ignore_index=True)
    
    print(f"✓ Loaded {len(df):,} pricing records")
    print(f"  - Unique drugs (NDC): {df['NDC'].nunique():,}")
    print(f"  - Days supply options: {sorted(df['DAYS_SUPPLY'].unique())}")
    print(f"  - Unit cost range: ${df['UNIT_COST'].min():.4f} - ${df['UNIT_COST'].max():.2f}")
    print(f"  - Median unit cost: ${df['UNIT_COST'].median():.4f}")
    
    return df

# Usage
pricing = read_pricing(f'{DATA_PATH}pricing file PPUF_2025Q3.txt')


PHARMACY_NETWORK_SCHEMA = {
    'CONTRACT_ID': str,
    'PLAN_ID': str,
    'SEGMENT_ID': str,
    'PHARMACY_NUMBER': str,
    'PHARMACY_ZIPCODE': str,
    'PREFERRED_STATUS_RETAIL': str,
    'PREFERRED_STATUS_MAIL': str,
    'PHARMACY_RETAIL': str,
    'PHARMACY_MAIL': str,
    'IN_AREA_FLAG': int,
    'FLOOR_PRICE': float,
    'BRAND_DISPENSING_FEE_30': float,
    'BRAND_DISPENSING_FEE_60': float,
    'BRAND_DISPENSING_FEE_90': float,
    'GENERIC_DISPENSING_FEE_30': float,
    'GENERIC_DISPENSING_FEE_60': float,
    'GENERIC_DISPENSING_FEE_90': float
}

def read_pharmacy_network(file_path, chunksize=CHUNK_SIZE):
    """
    Read PHARMACY_NETWORKS_FILE (very large - use chunks)
    """
    chunks = []
    
    for chunk in pd.read_csv(
        file_path,
        dtype=PHARMACY_NETWORK_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        chunksize=chunksize,
        delimiter='|'
    ):
        # Clean identifiers
        chunk['CONTRACT_ID'] = chunk['CONTRACT_ID'].str.strip()
        chunk['PLAN_ID'] = chunk['PLAN_ID'].str.strip()
        chunk['SEGMENT_ID'] = chunk['SEGMENT_ID'].str.strip().fillna('000')
        chunk['PHARMACY_NUMBER'] = chunk['PHARMACY_NUMBER'].str.strip()
        
        # Create keys
        chunk['PLAN_KEY'] = chunk['CONTRACT_ID'] + chunk['PLAN_ID'] + chunk['SEGMENT_ID']
        chunk['NETWORK_KEY'] = chunk['PLAN_KEY'] + '_' + chunk['PHARMACY_NUMBER']
        
        # Boolean flags
        chunk['IS_PREFERRED_RETAIL'] = chunk['PREFERRED_STATUS_RETAIL'] == 'Y'
        chunk['IS_PREFERRED_MAIL'] = chunk['PREFERRED_STATUS_MAIL'] == 'Y'
        chunk['OFFERS_RETAIL'] = chunk['PHARMACY_RETAIL'] == 'Y'
        chunk['OFFERS_MAIL'] = chunk['PHARMACY_MAIL'] == 'Y'
        chunk['IS_IN_AREA'] = chunk['IN_AREA_FLAG'] == 1
        
        # Calculate average dispensing fees
        chunk['AVG_BRAND_FEE'] = chunk[[
            'BRAND_DISPENSING_FEE_30',
            'BRAND_DISPENSING_FEE_60',
            'BRAND_DISPENSING_FEE_90'
        ]].mean(axis=1)
        
        chunk['AVG_GENERIC_FEE'] = chunk[[
            'GENERIC_DISPENSING_FEE_30',
            'GENERIC_DISPENSING_FEE_60',
            'GENERIC_DISPENSING_FEE_90'
        ]].mean(axis=1)
        
        # Pharmacy type classification
        chunk['PHARMACY_TYPE'] = 'standard'
        chunk.loc[chunk['IS_PREFERRED_RETAIL'], 'PHARMACY_TYPE'] = 'preferred_retail'
        chunk.loc[chunk['IS_PREFERRED_MAIL'] & chunk['OFFERS_MAIL'], 'PHARMACY_TYPE'] = 'preferred_mail'
        
        chunks.append(chunk)
    
    df = pd.concat(chunks, ignore_index=True)
    
    print(f"✓ Loaded {len(df):,} pharmacy network records")
    print(f"  - Unique pharmacies: {df['PHARMACY_NUMBER'].nunique():,}")
    print(f"  - Preferred retail: {df['IS_PREFERRED_RETAIL'].sum():,} ({df['IS_PREFERRED_RETAIL'].mean()*100:.1f}%)")
    print(f"  - Mail-order: {df['OFFERS_MAIL'].sum():,} ({df['OFFERS_MAIL'].mean()*100:.1f}%)")
    print(f"  - In-area: {df['IS_IN_AREA'].sum():,} ({df['IS_IN_AREA'].mean()*100:.1f}%)")
    
    return df

# Usage
pharmacy_network = read_pharmacy_network(f'{DATA_PATH}pharmacy networks file  PPUF_2025Q3 part 1.txt')


GEOGRAPHIC_SCHEMA = {
    'COUNTY_CODE': str,
    'STATENAME': str,
    'COUNTY': str,
    'MA_REGION_CODE': str,
    'MA_REGION': str,
    'PDP_REGION_CODE': str,
    'PDP_REGION': str
}

def read_geographic_locator(file_path):
    """
    Read GEOGRAPHIC_LOCATOR_FILE
    """
    df = pd.read_csv(
        file_path,
        dtype=GEOGRAPHIC_SCHEMA,
        na_values=['', ' ', 'NULL', 'NA'],
        delimiter='|'
    )
    
    # Clean text fields
    df['COUNTY_CODE'] = df['COUNTY_CODE'].str.strip()
    df['STATENAME'] = df['STATENAME'].str.strip()
    df['COUNTY'] = df['COUNTY'].str.strip()
    
    # Convert region codes to numeric
    df['MA_REGION_CODE_NUM'] = pd.to_numeric(df['MA_REGION_CODE'], errors='coerce')
    df['PDP_REGION_CODE_NUM'] = pd.to_numeric(df['PDP_REGION_CODE'], errors='coerce')
    
    # Extract state code from county code (first 2 digits)
    df['STATE_CODE'] = df['COUNTY_CODE'].str[:2]
    
    # Create readable location string
    df['LOCATION'] = df['COUNTY'] + ', ' + df['STATENAME']
    
    print(f"✓ Loaded {len(df):,} geographic mappings")
    print(f"  - States: {df['STATENAME'].nunique():,}")
    print(f"  - Counties: {df['COUNTY'].nunique():,}")
    print(f"  - MA Regions: {df['MA_REGION_CODE_NUM'].nunique():,}")
    print(f"  - PDP Regions: {df['PDP_REGION_CODE_NUM'].nunique():,}")
    
    return df

# Usage
geographic = read_geographic_locator(f'{DATA_PATH}geographic locator file PPUF_2025Q3.txt')
