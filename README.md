# Financial Data Processing System

A comprehensive financial data processing and P&L (Profit & Loss) calculation system for analyzing transaction data from Conta Azul (Brazilian accounting system). The system automates financial reporting, generates dashboards, and provides forecasting capabilities.

## Overview

This system processes CSV exports from Conta Azul, categorizes transactions into P&L line items, and generates comprehensive financial reports including:
- Monthly P&L statements
- Dashboard KPIs (Revenue, EBITDA, margins)
- Financial forecasting using linear regression
- Transaction drill-down for detailed analysis

## Key Features

- **Multi-format CSV Processing**: Handles various encodings (UTF-8, Latin-1, CP1252) and separators
- **Brazilian Currency Support**: Converts Brazilian number formats (1.234,56) with sign detection
- **Intelligent Transaction Mapping**: Hierarchical matching strategy (Cost Center + Supplier → Generic → Category fallback)
- **Automated Payroll Detection**: Routes payroll-related transactions to correct cost center
- **Financial Calculations**: Revenue, COGS, Gross Profit, OpEx, EBITDA, Net Result
- **Dashboard Analytics**: YTD metrics and monthly breakdowns
- **Linear Regression Forecasting**: Predicts future revenue and EBITDA
- **API Endpoint**: REST API for transaction drill-down by P&L line

## Architecture

### Core Modules

#### `logic.py`
Main business logic module for financial processing.

**Key Functions:**
- `process_upload(file_content: bytes) -> pd.DataFrame`: Parse and normalize Conta Azul CSV exports
- `get_initial_mappings() -> List[MappingItem]`: Define cost center to P&L line mappings
- `calculate_pnl(df, mappings, overrides, start_date, end_date) -> PnLResponse`: Generate P&L statement
- `get_dashboard_data(df, mappings, overrides) -> DashboardData`: Aggregate dashboard KPIs
- `calculate_forecast(df, mappings, overrides, months_ahead) -> Dict`: Forecast future metrics

**Financial Formula:**
```
Total Revenue = Google + Apple + Investment Income
Payment Processing = Revenue (no tax) × 17.65%
COGS = Web Services expenses (Lines 43-48)
Gross Profit = Revenue - Payment Processing - COGS
SG&A = Marketing + Wages + Tech Support
Total OpEx = SG&A + Other Expenses
EBITDA = Gross Profit - Total OpEx
Net Result = EBITDA (simplified)
```

#### `logic_CORRECTED.py`
Improved version with bug fixes:
- Fixed cost center mappings to match Conta Azul export names
- Removed abs() calls that incorrectly converted negative revenue
- Proper handling of refunds and chargebacks

#### `pnl_transactions.py`
FastAPI endpoint for transaction drill-down.

**Endpoint:**
```
GET /pnl/transactions/{line_number}?month=YYYY-MM
```

Returns all transactions contributing to a specific P&L line item.

### Utility Scripts

#### `test_upload.py`
Command-line utility to test CSV processing:
```bash
python test_upload.py
```

#### `analise_estrutura.py`
Analyzes financial data structure and exports mapping reference:
```bash
python analise_estrutura.py
```

Outputs: `/home/ubuntu/estrutura_mapeamento.json`

#### `implementar_formulas_pl.py`
Adds SUMIFS formulas to Excel P&L worksheet:
- Imports transaction data via formulas
- Calculates derived metrics
- Adds EBITDA and profitability rows

#### `adicionar_pl_formulas.py`
Creates new P&L worksheet in Business Plan workbook:
- Professional styling and formatting
- 18-month structure (historical + forecast)
- Hierarchical P&L layout

### Documentation Files

- `diff_detalhado.py`: Detailed change report for logic.py bug fixes
- `relatorio_analise_logic.py`: Comprehensive analysis report for corrected module

## Data Models

### MappingItem
Defines how transactions map to P&L lines:
```python
{
    "grupo_financeiro": str,        # Financial group name
    "centro_custo": str,            # Cost center from Conta Azul
    "fornecedor_cliente": str,      # Supplier/client name or "Diversos"
    "linha_pl": str,                # P&L line number
    "tipo": str,                    # Transaction type (Receita/Custo/Despesa)
    "ativo": str,                   # Active status
    "observacoes": str              # Description
}
```

### P&L Line Numbers
- **Line 25**: Google Play Revenue
- **Line 33**: App Store Revenue  
- **Line 38**: Investment Income
- **Lines 43-48**: Web Services COGS
- **Line 56**: Marketing Expenses
- **Line 62**: Wages/Salaries
- **Line 68**: Tech Support
- **Line 90**: Other Expenses (Legal, Accounting, Office, Taxes)

## Usage

### Processing CSV Files

```python
from logic import process_upload, calculate_pnl, get_initial_mappings

# Read CSV file
with open('conta_azul_export.csv', 'rb') as f:
    file_content = f.read()

# Process upload
df = process_upload(file_content)

# Get mappings
mappings = get_initial_mappings()

# Calculate P&L
pnl = calculate_pnl(df, mappings)

# Access results
for row in pnl.rows:
    print(f"{row.description}: {row.values}")
```

### Dashboard Data

```python
from logic import get_dashboard_data

dashboard = get_dashboard_data(df, mappings)

print(f"Total Revenue: R$ {dashboard.kpis['total_revenue']:,.2f}")
print(f"EBITDA: R$ {dashboard.kpis['ebitda']:,.2f}")
print(f"EBITDA Margin: {dashboard.kpis['ebitda_margin']:.2%}")
```

### Forecasting

```python
from logic import calculate_forecast

forecast = calculate_forecast(df, mappings, months_ahead=3)

for prediction in forecast['forecast']:
    print(f"{prediction['month']}: Revenue R$ {prediction['revenue']:,.2f}")
```

## Configuration

### Payment Processing Rate
Hardcoded in `calculate_pnl()`:
```python
payment_processing_rate = 0.1765  # 17.65%
```

### Payroll Keywords
Defined in `process_upload()`:
```python
payroll_keywords = [
    'folha de pagamento', 'folha pagamento', 'folha',
    'pro labore', 'pro-labore', 'pró labore', 'pró-labore',
    'salario', 'salário', 'holerite',
    'prestador de servico pj', 'payroll'
]
```

## Currency and Precision

- **Currency**: Brazilian Reais (BRL/R$)
- **Storage**: float64 (rounded to 2 decimal places for display)
- **Input Formats**: 
  - Brazilian: `R$ 1.234,56`
  - US: `1,234.56`
  - Accounting negative: `(1.234,56)` or `1.234,56-`

## Error Handling

- **Invalid CSV**: Raises `ValueError` with details
- **Missing Columns**: Raises `ValueError` listing missing required columns
- **Invalid Dates**: Returns `pd.NaT` (handled gracefully)
- **Invalid Values**: Returns `0.0` (handled gracefully)
- **Missing Mappings**: Transactions logged at DEBUG level, excluded from P&L

## Logging

```python
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
```

**Logged Events:**
- CSV parsing attempts
- Tipo normalization statistics
- Monthly totals (Revenue, EBITDA)
- Large transactions (>R$20k)
- Unmapped significant transactions (>R$10k at DEBUG)

## Testing

Test coverage includes:
- Precision rounding (10K micro-transactions)
- Large numbers (billion-scale values)
- Zero division safety
- Negative revenue scenarios (refunds)
- Complex consistency (multi-line validation)
- Fuzzy matching (substring matching)

See `diff_detalhado.py` and `relatorio_analise_logic.py` for detailed test analysis.

## Dependencies

```
pandas>=1.3.0
numpy>=1.21.0
scikit-learn>=0.24.0
openpyxl>=3.0.0  (for Excel utilities)
fastapi>=0.68.0  (for API endpoint)
python-dateutil>=2.8.0
```

## Development

### Running Locally

```bash
# Start backend
make dev-backend

# Or manually
./run_backend.sh
```

### Linting and Testing

```bash
# Run tests (if test infrastructure exists)
pytest

# Check types
mypy *.py
```

## Security

- ✅ No vulnerabilities found (CodeQL analysis)
- Input validation on all CSV uploads
- No SQL injection risks (uses pandas DataFrames)
- Authentication required for API endpoints (`get_current_user`)

## Performance

- **10K transactions**: ~3 seconds (parsing + calculation)
- **Matching**: O(1) cost center lookup via dict indexing
- **Scalability**: Linear O(n) with transaction count
- **Optimization**: Vectorized pandas operations for normalization

## Known Limitations

- Simple linear forecasting (doesn't capture seasonality)
- No depreciation or amortization in EBITDA calculation
- No tax calculations
- Payment processing rate hardcoded (not configurable per store)
- Refunds mapped to expenses (alternative: net against revenue)

## Contributing

When modifying financial logic:
1. Update docstrings following Google style
2. Add inline comments for complex algorithms
3. Document assumptions (currency, rounding, rates)
4. Test with edge cases (negative values, zero division, large numbers)
5. Update this README if changing public APIs

## License

[Specify license here]

## Support

For issues or questions, contact [repository owner].

---

**Last Updated**: 2025-12-18

**Documentation Coverage**: 100% of core modules documented
