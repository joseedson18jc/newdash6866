"""
Financial Data Processing and P&L Calculation Module.

This module provides core business logic for processing financial transactions from
Conta Azul (Brazilian accounting system) and generating Profit & Loss (P&L) statements,
dashboards, and financial forecasts.

Main Components:
    - CSV data parsing and normalization (multiple encodings, formats)
    - Transaction categorization and mapping to P&L lines
    - Financial calculations (revenue, costs, EBITDA, margins)
    - Dashboard KPI generation
    - Linear regression-based financial forecasting

Dependencies:
    - pandas: Data manipulation and analysis
    - numpy: Numerical computations
    - sklearn: Machine learning for forecasting
    - models: Data models (MappingItem, PnLItem, PnLResponse, DashboardData)

Side Effects:
    - Logging of financial calculations and warnings
    - No direct file I/O (data passed as bytes/DataFrames)

Currency Assumptions:
    - All monetary values in Brazilian Reais (BRL/R$)
    - Values stored as float64 (rounded to 2 decimal places for display)
    - Payment processing rate hardcoded at 17.65%
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime
import io
import logging
from typing import List, Dict, Any
from collections import defaultdict
import unicodedata
from models import MappingItem, PnLItem, PnLResponse, DashboardData

# Configure logging for financial calculations
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def process_upload(file_content: bytes) -> pd.DataFrame:
    """
    Process and normalize uploaded CSV file from Conta Azul accounting system.
    
    Handles multiple CSV formats, encodings, and separator types commonly exported
    by Conta Azul. Performs data cleaning, normalization, and validation to ensure
    consistent processing downstream.
    
    Args:
        file_content: Raw CSV file content as bytes.
        
    Returns:
        Processed DataFrame with normalized columns and computed fields:
            - Data de competência: Parsed datetime
            - Valor_Num: Numeric value with correct sign (+ for revenue, - for expense)
            - Mes_Competencia: Month period for aggregation
            - Centro de Custo 1: Normalized cost center
            - Nome do fornecedor/cliente: Normalized supplier/client name
            
    Raises:
        ValueError: If file cannot be parsed or missing required columns.
        
    Side Effects:
        - Prints parsing attempts and column mappings to stdout
        - Logs tipo normalization statistics
        
    Notes:
        - Tries multiple encoding/separator combinations automatically
        - Handles Brazilian number format (1.234,56)
        - Enforces payroll transactions to 'Wages Expenses' cost center
        - Preserves sign based on 'Tipo' column (Entrada/Saída)
    """
    # Try different encodings and separators
    df = None
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
    separators = [',', ';', '\t']
    last_error = None
    
    for encoding in encodings:
        for sep in separators:
            try:
                # Try strict parsing first
                df = pd.read_csv(io.BytesIO(file_content), encoding=encoding, sep=sep)
                
                # Check if it has the critical column 'Data de competência'
                if 'Data de competência' in df.columns:
                    break
                else:
                    df = None # Not the right separator
            except Exception:
                continue
        
        if df is not None:
            break
            
        # If strict parsing failed for this encoding, try with on_bad_lines='skip' as fallback
        for sep in separators:
            try:
                print(f"⚠️ Strict parsing failed. Retrying with on_bad_lines='skip', encoding={encoding}, sep='{sep}'")
                df = pd.read_csv(io.BytesIO(file_content), encoding=encoding, sep=sep, on_bad_lines='skip', engine='python')
                if 'Data de competência' in df.columns:
                    break
                else:
                    df = None
            except Exception as e:
                last_error = e
                continue
        
        if df is not None:
            break
    
    if df is None:
        if last_error:
            raise ValueError(f"Error reading CSV file. Please ensure it's a valid CSV. Details: {last_error}")
        else:
            raise ValueError("Error reading CSV file. Could not detect valid format (encoding/separator).")

    # Normalize column names - strip whitespace
    df.columns = [c.strip() for c in df.columns]
    
    # Column name mapping for flexibility (handle different Conta Azul export formats)
    column_aliases = {
        'Data de competência': ['Data de competência', 'Data de Competência', 'Data Competência', 'data_competencia', 'Data'],
        'Valor (R$)': ['Valor (R$)', 'Valor', 'Valor R$', 'valor', 'VALOR'],
        'Tipo': [
            'Tipo', 'tipo',
            'Entrada/Saída', 'Entrada/Saida',
            'Tipo (Entrada/Saída)', 'Tipo (Entrada/Saida)',
            'Tipo de movimentação', 'Tipo de Movimentação',
            'Natureza', 'natureza'
        ],
        'Centro de Custo 1': ['Centro de Custo 1', 'Centro de Custo', 'CentroCusto', 'centro_custo', 'Centro de custo 1'],
        'Nome do fornecedor/cliente': ['Nome do fornecedor/cliente', 'Fornecedor/Cliente', 'Nome Fornecedor', 'fornecedor_cliente', 'Fornecedor', 'Cliente']
    }
    
    # Try to find and rename columns
    for target_col, aliases in column_aliases.items():
        if target_col not in df.columns:
            for alias in aliases:
                if alias in df.columns:
                    df.rename(columns={alias: target_col}, inplace=True)
                    print(f"✅ Mapped column '{alias}' -> '{target_col}'")
                    break
    
    # Print available columns for debugging
    print(f"📋 Available columns after normalization: {list(df.columns)}")

    # Basic validation
    required_cols = ['Data de competência', 'Valor (R$)', 'Centro de Custo 1', 'Nome do fornecedor/cliente']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        available = ', '.join(df.columns[:10])  # Show first 10 columns
        raise ValueError(f"Missing required columns: {missing_cols}. Available columns: {available}...")

    # Data cleaning and normalization
    
    # Robust date parsing - tries multiple common date formats
    def parse_dates(date_str):
        """
        Parse date strings in multiple formats (Brazilian DD/MM/YYYY, ISO, US).
        Returns pd.NaT for invalid/missing dates.
        """
        if pd.isna(date_str): return pd.NaT
        date_str = str(date_str).strip()
        # Try formats in order: Brazilian (most common), ISO, US, dash-separated
        formats = ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y']
        for fmt in formats:
            try:
                return pd.to_datetime(date_str, format=fmt)
            except:
                continue
        return pd.NaT

    df['Data de competência'] = df['Data de competência'].apply(parse_dates)
    
    def normalize_text(s: Any) -> str:
        if pd.isna(s):
            return ""
        s = str(s).strip().lower()
        s = unicodedata.normalize("NFKD", s)
        return "".join(ch for ch in s if not unicodedata.combining(ch))
    
    def converter_valor_br(valor_str: Any) -> float:
        """
        Convert Brazilian currency strings to float with proper sign handling.
        
        Handles multiple formats:
        - Brazilian: R$ 1.234,56 (thousands separator ., decimal ,)
        - US: 1,234.56 (thousands separator ,, decimal .)
        - Accounting negative: (1.234,56) or 1.234,56-
        
        Returns 0.0 for invalid/empty values.
        """
        if pd.isna(valor_str) or str(valor_str).strip() == "":
            return 0.0

        # Remove currency symbol
        s = str(valor_str).replace('R$', '').strip()

        negative = False
        # Detect accounting-style negative: (1.234,56)
        if s.startswith('(') and s.endswith(')'):
            negative = True
            s = s[1:-1].strip()

        # Detect trailing minus: 1.234,56-
        if s.endswith('-'):
            negative = True
            s = s[:-1].strip()

        # Remove spaces
        s = s.replace(' ', '')

        # Disambiguate thousands vs decimal separator
        # If both ',' and '.' present, rightmost is decimal separator
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                # Brazilian format: 1.234,56 → remove . (thousands), convert , to . (decimal)
                s = s.replace('.', '').replace(',', '.')
            else:
                # US format: 1,234.56 → remove , (thousands), keep . (decimal)
                s = s.replace(',', '')
        elif ',' in s:
            # Only comma: assume decimal separator (Brazilian)
            s = s.replace(',', '.')

        try:
            v = float(s)
            return -v if negative else v
        except ValueError:
            return 0.0

    df['Valor_Num'] = df['Valor (R$)'].apply(converter_valor_br)

    # Apply transaction type (Entrada/Saída) to determine sign
    if 'Tipo' in df.columns:
        tipo = df['Tipo'].apply(normalize_text)

        # Identify expenses/debits (should be negative)
        # "Saída" = outflow, "Débito" = debit, "Despesa" = expense, "Pagamento" = payment
        is_saida = (
            tipo.str.contains('saida') |
            tipo.str.contains('debito') |
            tipo.str.contains('despesa') |
            tipo.str.contains('pagamento')
        )
        # Entrada/Credito/Receita → positive sign (+1.0)
        # Saída/Débito/Despesa/Pagamento → negative sign (-1.0)
        sign = np.where(is_saida, -1.0, 1.0)

        # CRITICAL: Use Tipo column as source of truth for sign
        # Override any embedded minus from converter_valor_br
        # Take absolute value then apply correct sign based on Tipo
        df['Valor_Num'] = df['Valor_Num'].abs() * sign
        
        # Validation logging for debugging
        logger.info("Tipo normalization applied.")
        logger.info(f"Tipo counts: {tipo.value_counts().to_dict()}")
        logger.info(f"Sum Valor_Num (signed): {df['Valor_Num'].sum():.2f}")
        logger.info(f"Sum abs Valor_Num: {df['Valor_Num'].abs().sum():.2f}")
    else:
        # Fallback: if no Tipo column, rely on sign from converter_valor_br
        logger.warning("CSV has no Tipo/Entrada-Saída column; using sign embedded in Valor (R$).")
    df['Mes_Competencia'] = df['Data de competência'].dt.to_period('M')
    
    # Normalize text columns for mapping
    if 'Centro de Custo 1' in df.columns:
        df['Centro de Custo 1'] = df['Centro de Custo 1'].astype(str).str.strip()
    if 'Nome do fornecedor/cliente' in df.columns:
        df['Nome do fornecedor/cliente'] = df['Nome do fornecedor/cliente'].astype(str).str.strip()
    if 'Categoria 1' in df.columns:
        df['Categoria 1'] = df['Categoria 1'].astype(str).str.strip()

    # Ensure payroll transactions are routed to Wages Expenses (P&L line 62)
    # This enforces consistent categorization even if cost center is wrong in Conta Azul
    payroll_keywords = [
        'folha de pagamento', 'folha pagamento', 'folha',
        'pro labore', 'pro-labore', 'pró labore', 'pró-labore',
        'salario', 'salário', 'holerite',
        'prestador de servico pj', 'payroll'
    ]

    def enforce_wages_cost_center(row):
        """
        Detect and reroute payroll transactions to 'Wages Expenses' cost center.
        
        Searches for payroll keywords in Categoria, Descrição, and Fornecedor fields.
        Overrides Centro de Custo if payroll indicators found.
        """
        current_cc = str(row.get('Centro de Custo 1', '') or '').strip()
        cc_norm = normalize_text_helper(current_cc)

        # Already correctly tagged - no change needed
        if cc_norm == 'wages expenses':
            return 'Wages Expenses'

        # Build combined search text from multiple fields
        combined_text = ' '.join([
            normalize_text_helper(row.get('Categoria 1', '')),
            normalize_text_helper(row.get('Descrição', '')),
            normalize_text_helper(row.get('Nome do fornecedor/cliente', ''))
        ])

        # Check if any payroll keyword appears in combined text
        if any(keyword in combined_text for keyword in payroll_keywords):
            return 'Wages Expenses'

        # No payroll indicators - keep original cost center
        return current_cc

    df['Centro de Custo 1'] = df.apply(enforce_wages_cost_center, axis=1)

    return df

def get_initial_mappings() -> List[MappingItem]:
    """
    Return predefined mappings from cost centers/suppliers to P&L line items.
    
    Defines how transactions from Conta Azul are categorized into specific P&L
    statement lines. Includes both specific mappings (cost center + supplier)
    and generic fallback mappings (cost center + "Diversos").
    
    Returns:
        List of MappingItem objects containing:
            - grupo_financeiro: Financial group name
            - centro_custo: Cost center from Conta Azul
            - fornecedor_cliente: Supplier/client name (or "Diversos" for generic)
            - linha_pl: P&L line number (as string)
            - tipo: Transaction type (Receita/Custo/Despesa)
            - ativo: Active status ("Sim")
            - observacoes: Human-readable description
            
    Notes:
        - Line 25: Google Play Revenue
        - Line 33: App Store Revenue
        - Line 38: Investment Income
        - Line 43-48: Web Services COGS
        - Line 56: Marketing Expenses
        - Line 62: Wages/Salaries
        - Line 68: Tech Support
        - Line 90: Other Expenses (Legal, Accounting, Office, Taxes, etc.)
        - Generic "Diversos" mappings serve as fallbacks when specific supplier not matched
    """
    # Helper to condense definition
    def m(cc, supp, line, tipo, obs):
        return MappingItem(
            grupo_financeiro=cc,
            centro_custo=cc,
            fornecedor_cliente=supp,
            linha_pl=str(line),
            tipo=tipo,
            ativo="Sim",
            observacoes=obs
        )

    mappings = [
        # RECEITAS (Revenues)
        m("Receita Google", "GOOGLE BRASIL PAGAMENTOS LTDA", 25, "Receita", "Receita Google Play"),
        m("Receita Apple", "App Store (Apple)", 33, "Receita", "Receita App Store"),
        m("Rendimentos de Aplicações", "CONTA SIMPLES", 38, "Receita", "Rendimentos CDI"),
        m("Rendimentos de Aplicações", "BANCO INTER", 38, "Receita", "Rendimentos Inter"),
        
        # COGS (Direct Costs)
        # Specific
        m("Web Services Expenses", "AWS", 43, "Custo", "Amazon Web Services"),
        m("Web Services Expenses", "Cloudflare", 44, "Custo", "Cloudflare"),
        m("Web Services Expenses", "Heroku", 45, "Custo", "Heroku"),
        m("Web Services Expenses", "IAPHUB", 46, "Custo", "IAPHUB"),
        m("Web Services Expenses", "MailGun", 47, "Custo", "MailGun"),
        m("Web Services Expenses", "AWS SES", 48, "Custo", "AWS SES"),
        # Generic
        m("Web Services Expenses", "Diversos", 43, "Custo", "Web Services - Generic"),

        # SG&A (Operating Expenses)
        # Marketing
        m("Marketing & Growth Expenses", "MGA MARKETING LTDA", 56, "Despesa", "Marketing Agency"),
        m("Marketing & Growth Expenses", "Diversos", 56, "Despesa", "Marketing - Generic"),
        
        # Wages
        m("Wages Expenses", "Diversos", 62, "Despesa", "Salários e Pró-labore"),
        
        # Tech Support
        m("Tech Support & Services", "Adobe", 68, "Despesa", "Adobe Creative Cloud"),
        m("Tech Support & Services", "Canva", 68, "Despesa", "Canva"),
        m("Tech Support & Services", "ClickSign", 68, "Despesa", "ClickSign"),
        m("Tech Support & Services", "COMPANYHERO", 68, "Despesa", "Company Hero"),
        m("Tech Support & Services", "Diversos", 65, "Despesa", "Tech Support - Generic"),
        
        # OTHER EXPENSES / TAXES
        # Legal & Accounting
        m("Legal & Accounting Expenses", "BHUB.AI", 90, "Despesa", "BPO Financeiro"),
        m("Legal & Accounting Expenses", "WOLFF", 90, "Despesa", "Honorários Advocatícios"),
        m("Legal & Accounting Expenses", "Diversos", 90, "Despesa", "Legal & Accounting - Generic"),

        # Office
        m("Office Expenses", "GO OFFICES", 90, "Despesa", "Aluguel"),
        m("Office Expenses", "CO-SERVICES", 90, "Despesa", "Serviços de Escritório"),
        m("Office Expenses", "Diversos", 90, "Despesa", "Office Expenses - Generic"),

        # Travel
        m("Travel", "American Airlines", 90, "Despesa", "Viagens"),
        m("Travel", "Diversos", 90, "Despesa", "Travel - Generic"),

        # Taxes
        m("Other Taxes", "IMPOSTOS/TRIBUTOS", 90, "Despesa", "Impostos e Tributos"),
        m("Other Taxes", "Diversos", 90, "Despesa", "Other Taxes - Generic"),
        m("Payroll Tax - Brazil", "IMPOSTOS/TRIBUTOS", 90, "Despesa", "Impostos sobre Folha"),
        m("Payroll Tax - Brazil", "Diversos", 90, "Despesa", "Payroll Tax - Generic"),

        # General / Catch-all
        m("Other Expenses", "Diversos", 90, "Despesa", "Despesas Gerais"),
        m("Identificar", "Diversos", 90, "Despesa", "Despesas a Identificar"),
        m("Devoluções e Estornos", "Diversos", 90, "Despesa", "Refunds & Chargebacks"),
    ]
    return mappings

def normalize_text_helper(s: Any) -> str:
    """
    Normalize text for consistent case-insensitive matching.
    
    Converts to lowercase, strips whitespace, and removes diacritical marks
    (accents) to enable robust fuzzy matching of cost centers and supplier names.
    
    Args:
        s: Input string or value to normalize (can be NaN, None, or any type).
        
    Returns:
        Normalized lowercase string without accents, or empty string for NaN/None.
        
    Examples:
        >>> normalize_text_helper("São Paulo  ")
        'sao paulo'
        >>> normalize_text_helper("TÉCNICO")
        'tecnico'
        >>> normalize_text_helper(None)
        ''
    """
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def prepare_mappings(mappings: List[MappingItem]):
    """
    Optimize mappings for fast lookup during P&L calculation.
    
    Separates mappings into two categories for efficient matching:
    1. Specific mappings: cost center + specific supplier
    2. Generic mappings: cost center + "Diversos" (fallback)
    
    Args:
        mappings: List of MappingItem objects from get_initial_mappings().
        
    Returns:
        Tuple of (specific_by_cc, generic_by_cc):
            - specific_by_cc: Dict[str, List[MappingItem]] indexed by normalized cost center,
              sorted by supplier name length (longest first for most specific match)
            - generic_by_cc: Dict[str, MappingItem] indexed by normalized cost center
              
    Notes:
        - O(1) lookup by cost center instead of O(n) linear search
        - Longest supplier match first prevents "AWS" matching "AWS SES"
        - Generic mappings provide fallback when specific supplier not found
    """
    from collections import defaultdict
    
    # Use defaultdict(list) for specific mappings to handle multiple patterns for same CC
    specific_by_cc = defaultdict(list)
    generic_by_cc = {}

    for m in mappings:
        cc = normalize_text_helper(m.centro_custo)
        supp = normalize_text_helper(m.fornecedor_cliente)

        if supp and supp != "diversos":
            # Specific mapping
            specific_by_cc[cc].append(m)
        else:
            # Generic mapping (fallback)
            generic_by_cc[cc] = m

    # Sort specific mappings by supplier length desc (Longest match first)
    for cc, m_list in specific_by_cc.items():
        m_list.sort(key=lambda x: len(normalize_text_helper(x.fornecedor_cliente)), reverse=True)

    return specific_by_cc, generic_by_cc

def calculate_pnl(df: pd.DataFrame, mappings: List[MappingItem], overrides: Dict[str, Dict[str, float]] = None, start_date: str = None, end_date: str = None) -> PnLResponse:
    """
    Calculate comprehensive Profit & Loss statement from transaction data.
    
    Maps transactions to P&L line items, aggregates by month, computes derived
    financial metrics (EBITDA, margins, etc.), and formats for display.
    
    Args:
        df: Processed DataFrame from process_upload() with transaction data.
        mappings: List of MappingItem objects defining cost center to P&L line mappings.
        overrides: Optional manual overrides for specific lines and months.
            Format: {"line_num": {"month_str": value}}
            Only lines 100 (Revenue), 106 (EBITDA), 111 (Net Result) allowed.
        start_date: Optional ISO date string (YYYY-MM-DD) for filtering.
        end_date: Optional ISO date string (YYYY-MM-DD) for filtering.
        
    Returns:
        PnLResponse containing:
            - headers: List of month strings (YYYY-MM format)
            - rows: List of PnLItem objects with line details and monthly values
            
    Raises:
        No exceptions raised; returns empty response if df is None/empty.
        
    Side Effects:
        - Logs monthly totals (Revenue, EBITDA) at INFO level
        - Logs large matches (>R$20k) at INFO level for debugging
        - Logs unmapped significant items (>R$10k) at DEBUG level
        
    Financial Calculations:
        1. Total Revenue = Google + Apple + Investment Income
        2. Payment Processing = Revenue (no tax) × 17.65%
        3. COGS = Web Services expenses
        4. Gross Profit = Revenue - Payment Processing - COGS
        5. SG&A = Marketing + Wages + Tech Support
        6. Total OpEx = SG&A + Other Expenses
        7. EBITDA = Gross Profit - Total OpEx
        8. Net Result = EBITDA (simplified, no D&A or taxes)
        
    Notes:
        - Revenue values preserve sign (negative for refunds/chargebacks)
        - Expenses displayed as negative in P&L
        - Margins calculated as percentage of total revenue
        - Unmapped transactions are ignored (logged at DEBUG level)
    """
    if df is None or df.empty:
        return PnLResponse(headers=[], rows=[])
    
    # Apply date filter if provided
    filtered_df = df.copy()
    if start_date or end_date:
        if start_date:
            start = pd.to_datetime(start_date)
            filtered_df = filtered_df[filtered_df['Data de competência'] >= start]
        if end_date:
            end = pd.to_datetime(end_date)
            filtered_df = filtered_df[filtered_df['Data de competência'] <= end]

    # Calculate months from filtered data
    months = sorted(filtered_df['Mes_Competencia'].dropna().unique())
    month_strs = [str(m) for m in months]

    # Initialize data structure for calculations
    # line_values[line_num][month_str] = value
    line_values = {i: {m: 0.0 for m in month_strs} for i in range(1, 121)}

    # Optimize Mapping Lookups - O(1) by cost center instead of O(n) linear search
    specific_mappings, generic_mappings = prepare_mappings(mappings)

    # DataFrame Enhancement for Matching
    # Pre-compute normalized columns for performance (vectorized operations)
    if 'Descrição' not in filtered_df.columns:
        filtered_df['Descrição'] = ''
    
    # Normalize all text fields used in matching (case-insensitive, no accents)
    filtered_df['cc_norm'] = filtered_df['Centro de Custo 1'].fillna('').apply(normalize_text_helper)
    filtered_df['supp_norm'] = filtered_df['Nome do fornecedor/cliente'].fillna('').apply(normalize_text_helper)
    filtered_df['desc_norm'] = filtered_df['Descrição'].fillna('').apply(normalize_text_helper)
    
    # Combined search text: supplier + description for substring matching
    # Enables matching supplier name mentioned in description field
    filtered_df['match_text'] = (filtered_df['supp_norm'] + " " + filtered_df['desc_norm']).str.strip()

    # Iterate through transactions and match to P&L lines
    # Uses hierarchical matching strategy: Specific → Generic → Categoria fallback
    for _, row in filtered_df.iterrows():
        month = str(row['Mes_Competencia'])
        if month not in month_strs:
            continue
            
        val = row['Valor_Num']
        cc = row['cc_norm']
        match_text = row['match_text']
        
        matched_mapping = None
        
        # === Hierarchical Matching Strategy ===
        
        # Level 1: Specific Mappings (Cost Center + Supplier substring match)
        # Try to match specific supplier within the cost center
        # Sorted by length (longest first) to match most specific pattern
        candidates = specific_mappings.get(cc, [])
        for m in candidates:
            m_supp_norm = normalize_text_helper(m.fornecedor_cliente)
            # Substring match: check if supplier name appears in combined text
            # Example: "aws" in "aws ireland" OR "paid to aws"
            if m_supp_norm in match_text:
                matched_mapping = m
                break
        
        # Level 2: Generic Mapping (Cost Center + "Diversos")
        # Fallback if no specific supplier matched
        if not matched_mapping:
            matched_mapping = generic_mappings.get(cc)
        
        # Level 3: Categoria 1 Fallback
        # If cost center didn't match, try Categoria 1 as alternative grouping
        if not matched_mapping and 'Categoria 1' in row:
            cat_cc = normalize_text_helper(row['Categoria 1'])
            # Try specific mappings for categoria
            candidates_cat = specific_mappings.get(cat_cc, [])
            for m in candidates_cat:
                m_supp_norm = normalize_text_helper(m.fornecedor_cliente)
                if m_supp_norm in match_text:
                    matched_mapping = m
                    break
            # Try generic mapping for categoria
            if not matched_mapping:
                matched_mapping = generic_mappings.get(cat_cc)

        # Accumulate value to matched P&L line
        if matched_mapping:
            try:
                line_num = int(matched_mapping.linha_pl)
                line_values[line_num][month] += val
                
                # DEBUG: Log large transactions for audit trail
                if abs(val) > 20000:
                    description = matched_mapping.observacoes
                    logger.info(f"MATCH: Line {line_num} ({description}) | Val: {val:.2f} | Basis: '{match_text}' matched '{matched_mapping.fornecedor_cliente}'")
            except:
                # Silently skip invalid line numbers
                continue
        else:
            # Log unmapped significant transactions for review
            # These transactions won't appear in P&L
            if abs(val) > 10000:
                logger.debug(f"UNMAPPED: {val:.2f} | CC: {cc} | Text: {match_text}")

    # ========================================================================
    # CALCULATE DERIVED FINANCIAL METRICS FOR EACH MONTH
    # ========================================================================
    # Aggregates raw line values into standard P&L structure following
    # accounting conventions: Revenue - COGS = Gross Profit - OpEx = EBITDA
    
    for m in month_strs:
        
        # ============================================
        # STEP 1: REVENUE AGGREGATION
        # ============================================
        # Line 25: Google Play Revenue (from Conta Azul)
        # Line 33: App Store Revenue (from Conta Azul)
        # Line 38: Investment Income (interest, CDI yields)
        # Line 49: Miscellaneous revenue (if any)
        
        # NOTE: abs() used here enforces positive revenue display convention
        # Refunds are mapped to Line 90 (Other Expenses) to preserve revenue as gross sales
        # See logic_CORRECTED.py for version that preserves sign for net revenue calculation
        google_rev = abs(line_values[25].get(m, 0.0))
        apple_rev = abs(line_values[33].get(m, 0.0))
        invest_income = abs(line_values[38].get(m, 0.0)) + abs(line_values[49].get(m, 0.0))
        
        total_revenue = google_rev + apple_rev + invest_income
        revenue_no_tax = google_rev + apple_rev  # Excludes investment income for fee calculation
        
        # ============================================
        # STEP 2: PAYMENT PROCESSING FEES
        # ============================================
        # Google and Apple charge 17.65% combined fees
        # (15% platform fee + additional processing fees)
        # Investment income doesn't incur these fees
        
        payment_processing_rate = 0.1765  # 17.65% hardcoded rate
        payment_processing_cost = revenue_no_tax * payment_processing_rate
        
        # ============================================
        # STEP 3: COST OF GOODS SOLD (COGS)
        # ============================================
        # Lines 43-48: Web Services (AWS, Cloudflare, Heroku, IAPHUB, MailGun, AWS SES)
        # Direct costs attributable to delivering the service
        
        cogs_sum = sum(abs(line_values[i].get(m, 0.0)) for i in range(43, 49))
        
        # ============================================
        # STEP 4: GROSS PROFIT
        # ============================================
        # Revenue minus all direct costs (payment processing + COGS)
        
        gross_profit = total_revenue - payment_processing_cost - cogs_sum
        
        # ============================================
        # STEP 5: OPERATING EXPENSES (OpEx)
        # ============================================
        # Line 56: Marketing & Growth
        # Line 62: Wages (salaries, pro-labore, payroll)
        # Lines 65, 68: Tech Support & Services (Adobe, Canva, etc.)
        # Line 90: Other Expenses (legal, accounting, office, taxes, refunds)
        
        marketing_abs = abs(line_values[56].get(m, 0.0))
        wages_abs = abs(line_values[62].get(m, 0.0))
        tech_support_abs = abs(line_values[68].get(m, 0.0)) + abs(line_values[65].get(m, 0.0))
        other_expenses_abs = abs(line_values[90].get(m, 0.0))
        
        # SG&A: Selling, General & Administrative expenses
        sga_total = marketing_abs + wages_abs + tech_support_abs
        total_opex = sga_total + other_expenses_abs
        
        # ============================================
        # STEP 6: EBITDA (Operating Profit)
        # ============================================
        # Earnings Before Interest, Taxes, Depreciation, Amortization
        # Simplified: no D&A or interest in this model
        
        ebitda = gross_profit - total_opex
        
        # ============================================
        # STEP 7: NET RESULT
        # ============================================
        # Simplified: EBITDA = Net Result (no taxes, D&A, or interest modeled)
        
        net_result = ebitda
        
        # ============================================
        # STORE CALCULATED VALUES FOR DISPLAY
        # ============================================
        # Convention: Revenue positive, Expenses negative
        
        line_values[100][m] = total_revenue           # Total Revenue
        line_values[101][m] = revenue_no_tax          # Revenue (no investment income)
        line_values[112][m] = google_rev              # Google Play breakdown
        line_values[113][m] = apple_rev               # App Store breakdown
        line_values[102][m] = -payment_processing_cost  # Payment fees (negative)
        line_values[103][m] = -cogs_sum               # COGS (negative)
        line_values[104][m] = gross_profit            # Gross Profit (positive)
        line_values[105][m] = -sga_total              # SG&A (negative)
        line_values[106][m] = ebitda                  # EBITDA (can be negative)
        line_values[107][m] = -marketing_abs          # Marketing detail (negative)
        line_values[108][m] = -wages_abs              # Wages detail (negative)
        line_values[109][m] = -tech_support_abs       # Tech support detail (negative)
        line_values[110][m] = -other_expenses_abs     # Other expenses detail (negative)
        line_values[111][m] = net_result              # Net Result
        
        # Log monthly summary for audit/debugging
        logger.info(f"Month {m}: Rev={total_revenue:.2f}, EBITDA={ebitda:.2f}")

    # APPLY OVERRIDES (Restricted to Final Lines)
    FINAL_LINES = {100, 106, 111} # Revenue, EBITDA, Net Result
    if overrides:
        for line_str, months_data in overrides.items():
            try:
                line_num = int(line_str)
                if line_num not in FINAL_LINES:
                    continue
                for m, val in months_data.items():
                    if m in month_strs:
                        line_values[line_num][m] = val
            except:
                continue

    # Build P&L Rows
    rows = []
    
    def add_row(line_num, desc, val_dict, is_header=False, is_total=False):
        # Check for override on this specific line (even if not in FINAL_LINES, to display user intent if blocked?)
        # For safety as requested, we strictly rely on the calc above, 
        # but if we want to show the overridden value we must read from line_values which we updated above.
        
        rows.append(PnLItem(
            line_number=line_num,
            description=desc,
            values=val_dict,
            is_header=is_header,
            is_total=is_total
        ))

    add_row(1, "RECEITA OPERACIONAL BRUTA", line_values[100], is_header=True)
    add_row(2, "Receita de Vendas (Google + Apple)", line_values[101])
    add_row(21, "Google Play Revenue", line_values[112])
    add_row(22, "App Store Revenue", line_values[113])
    add_row(3, "Rendimentos de Aplicações", line_values[38])
    
    add_row(4, "(-) CUSTOS DIRETOS", {m: line_values[102][m] + line_values[103][m] for m in month_strs}, is_header=True)
    add_row(5, "Payment Processing (17.65%)", line_values[102])
    add_row(6, "COGS (Web Services)", line_values[103])
    
    add_row(7, "(=) LUCRO BRUTO", line_values[104], is_total=True)
    
    add_row(8, "(-) DESPESAS OPERACIONAIS", {m: line_values[105][m] + line_values[110][m] for m in month_strs}, is_header=True)
    add_row(9, "Marketing", line_values[107])
    add_row(10, "Salários (Wages)", line_values[108])
    add_row(11, "Tech Support & Services", line_values[109])
    add_row(12, "Outras Despesas", line_values[110])
    
    add_row(13, "(=) EBITDA", line_values[106], is_total=True)
    add_row(16, "(=) RESULTADO LÍQUIDO", line_values[111], is_total=True)
    
    # Margins
    ebitda_margins = {}
    gross_margins = {}
    for m in month_strs:
        rev = line_values[100][m]
        if rev and rev != 0:
            ebitda_margins[m] = (line_values[106][m] / rev) * 100
            gross_margins[m] = (line_values[104][m] / rev) * 100
        else:
            ebitda_margins[m] = 0.0
            gross_margins[m] = 0.0
            
    add_row(14, "Margem EBITDA %", ebitda_margins)
    add_row(15, "Margem Bruta %", gross_margins)

    return PnLResponse(headers=month_strs, rows=rows)
def get_dashboard_data(df: pd.DataFrame, mappings: List[MappingItem], overrides: Dict[str, Dict[str, float]] = None) -> DashboardData:
    """
    Generate dashboard metrics and visualizations data from P&L.
    
    Aggregates P&L data into year-to-date KPIs, monthly trends, and cost structure
    breakdown for dashboard display.
    
    Args:
        df: Processed DataFrame from process_upload().
        mappings: List of MappingItem objects.
        overrides: Optional manual overrides (same format as calculate_pnl).
        
    Returns:
        DashboardData containing:
            - kpis: Dict with YTD aggregated metrics:
                * total_revenue: Sum across all months
                * net_result: Sum of net results
                * ebitda: Sum of EBITDA
                * ebitda_margin: Percentage (EBITDA / Revenue)
                * gross_margin: Percentage (Gross Profit / Revenue)
                * google_revenue: Sum of Google Play revenue
                * apple_revenue: Sum of App Store revenue
                * nau: Placeholder (0)
                * cpa: Placeholder (0)
            - monthly_data: List of dicts with per-month breakdown:
                * month: Month string (YYYY-MM)
                * revenue: Revenue for month
                * ebitda: EBITDA for month
                * costs: COGS (absolute value for positive display)
                * expenses: OpEx (absolute value for positive display)
            - cost_structure: Dict with latest month breakdown (absolute values):
                * payment_processing: Payment processing fees
                * cogs: Web services costs
                * marketing: Marketing expenses
                * wages: Salary expenses
                * tech: Tech support expenses
                * other: Other expenses
                
    Notes:
        - Returns empty structure if df is None
        - All cost/expense values converted to positive for chart display
        - Finds latest month with non-zero revenue for cost structure
    """
    if df is None:
        return DashboardData(kpis={}, monthly_data=[], cost_structure={})
        
    pnl = calculate_pnl(df, mappings, overrides)
    
    # Extract latest month data
    if not pnl.headers:
        return DashboardData(kpis={}, monthly_data=[], cost_structure={})
        
    # Find the latest month with non-zero revenue
    latest_month = pnl.headers[-1]
    for m in reversed(pnl.headers):
        # Check revenue for this month (Line 1 is Gross Revenue)
        rev = 0
        for row in pnl.rows:
            if row.line_number == 1: # RECEITA OPERACIONAL BRUTA
                rev = row.values.get(m, 0)
                break
        
        if rev > 0:
            latest_month = m
            break
    
    # Helper to find row value by line number
    def get_val_by_line(line_num, month):
        for row in pnl.rows:
            if row.line_number == line_num:
                return row.values.get(month, 0.0)
        return 0.0
    
    # Helper to find row value by description start
    def get_val(desc_start, month):
        for row in pnl.rows:
            if row.description.startswith(desc_start):
                return row.values.get(month, 0.0)
        return 0.0

    # Extract KPIs - SUM over all months (YTD view)
    total_revenue = 0.0
    total_ebitda = 0.0
    total_gross_profit = 0.0
    total_google = 0.0
    total_apple = 0.0
    
    # Iterate through all months to sum up values
    for m in pnl.headers:
        total_revenue += get_val_by_line(1, m)       # RECEITA OPERACIONAL BRUTA
        total_ebitda += get_val_by_line(13, m)       # EBITDA
        total_gross_profit += get_val_by_line(7, m)  # LUCRO BRUTO
        total_google += get_val_by_line(21, m)
        total_apple += get_val_by_line(22, m)
    
    total_net_result = 0.0
    for m in pnl.headers:
        total_net_result += get_val_by_line(16, m)      # (=) RESULTADO LÍQUIDO
    
    # Avoid division by zero
    ebitda_margin = (total_ebitda / total_revenue) if total_revenue > 0 else 0.0
    gross_margin = (total_gross_profit / total_revenue) if total_revenue > 0 else 0.0
    
    # KPIs
    kpis = {
        "total_revenue": total_revenue,
        "net_result": total_net_result,
        "ebitda": total_ebitda,
        "ebitda_margin": ebitda_margin,
        "gross_margin": gross_margin,
        "google_revenue": total_google,
        "apple_revenue": total_apple,
        "nau": 0,  # Placeholder
        "cpa": 0   # Placeholder
    }
    
    # Monthly Data for Charts
    monthly_data = []
    for m in pnl.headers:
        # Get values for this month
        month_revenue = get_val_by_line(1, m)
        month_ebitda = get_val_by_line(13, m)
        
        # Costs and expenses are stored as negative, convert to positive for charts
        month_cogs = abs(get_val_by_line(4, m))  # (-) CUSTOS DIRETOS total
        month_opex = abs(get_val_by_line(8, m))  # (-) DESPESAS OPERACIONAIS total
        
        monthly_data.append({
            "month": m,
            "revenue": month_revenue,
            "ebitda": month_ebitda,
            "costs": month_cogs,  # Positive for chart display
            "expenses": month_opex  # Positive for chart display
        })
        
    # Cost Structure (Latest Month) - all as positive values
    cost_structure = {
        "payment_processing": abs(get_val_by_line(5, latest_month)),  # Payment Processing
        "cogs": abs(get_val_by_line(6, latest_month)),  # COGS (Web Services)
        "marketing": abs(get_val_by_line(9, latest_month)),  # Marketing
        "wages": abs(get_val_by_line(10, latest_month)),  # Salários
        "tech": abs(get_val_by_line(11, latest_month)),  # Tech Support
        "other": abs(get_val_by_line(12, latest_month))  # Outras Despesas
    }
    
    
    return DashboardData(kpis=kpis, monthly_data=monthly_data, cost_structure=cost_structure)

def calculate_forecast(df: pd.DataFrame, mappings: List[MappingItem], overrides: Dict[str, Dict[str, float]] = None, months_ahead: int = 3) -> Dict[str, Any]:
    """
    Predict future financial metrics using linear regression on historical data.
    
    Trains separate linear models on revenue and EBITDA time series to forecast
    future months. Useful for simple trend projection.
    
    Args:
        df: Processed DataFrame from process_upload().
        mappings: List of MappingItem objects.
        overrides: Optional manual overrides (same format as calculate_pnl).
        months_ahead: Number of future months to forecast (default: 3).
        
    Returns:
        Dict containing:
            - forecast: List of dicts with predictions:
                * month: Future month string (YYYY-MM)
                * revenue: Predicted revenue (minimum 0)
                * ebitda: Predicted EBITDA
                * is_forecast: Always True
            - warning: Optional message if insufficient data (<3 months)
            
    Raises:
        No exceptions; returns empty forecast list if insufficient data.
        
    Notes:
        - Requires at least 3 historical months for reliable prediction
        - Uses sklearn LinearRegression (simple least-squares fit)
        - Revenue forecast clamped to non-negative values
        - EBITDA forecast can be negative
        - Simple linear model may not capture seasonality or non-linear trends
    """
    if df is None:
        return {"forecast": []}

    # Get historical data
    pnl = calculate_pnl(df, mappings, overrides)
    
    if not pnl.headers:
        return {"forecast": []}
        
    # Prepare data for regression
    # X = Month Index (0, 1, 2...), Y = Value
    
    # We need to parse month strings 'YYYY-MM' to ordinal or just index
    months_str = pnl.headers
    
    # Helper to get line values
    def get_line_series(line_number):
        series = []
        for m in months_str:
            val = 0.0
            for row in pnl.rows:
                if row.line_number == line_number:
                    val = row.values.get(m, 0.0)
                    break
            series.append(val)
        return series

    revenue_series = get_line_series(1) # Revenue
    ebitda_series = get_line_series(13) # EBITDA
    
    # Ensure sufficient data points (at least 3 months for a trend)
    if len(months_str) < 3:
        return {"forecast": [], "warning": "Not enough data for reliable forecast (need 3+ months)"}

    X = np.arange(len(months_str)).reshape(-1, 1)
    
    # Train Models
    model_rev = LinearRegression()
    model_rev.fit(X, revenue_series)
    
    model_ebitda = LinearRegression()
    model_ebitda.fit(X, ebitda_series)
    
    # Predict Future
    last_idx = len(months_str) - 1
    future_X = np.arange(last_idx + 1, last_idx + 1 + months_ahead).reshape(-1, 1)
    
    pred_rev = model_rev.predict(future_X)
    pred_ebitda = model_ebitda.predict(future_X)
    
    # Generate future month labels
    last_month_str = months_str[-1]
    last_date = pd.Period(last_month_str, freq='M')
    
    forecast_data = []
    for i in range(months_ahead):
        next_period = last_date + (i + 1)
        forecast_data.append({
            "month": str(next_period),
            "revenue": max(0, round(float(pred_rev[i]), 2)), # No negative revenue
            "ebitda": round(float(pred_ebitda[i]), 2),
            "is_forecast": True
        })
        
    return {"forecast": forecast_data}

