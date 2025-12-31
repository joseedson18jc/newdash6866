"""
P&L Transaction Drill-Down API Endpoint.

This module provides a FastAPI endpoint for retrieving detailed transaction data
that contributes to specific P&L line items. Enables drill-down analysis from
summary P&L statements to individual transactions.

Main Features:
    - Transaction filtering by P&L line number
    - Optional month filtering
    - Authentication required via dependency injection
    - Aggregates total value and transaction count

Dependencies:
    - FastAPI: Web framework for API endpoint
    - pandas: Data manipulation
    - auth: Authentication module (get_current_user)
    - main: Access to current_df and current_mappings (global state)

Side Effects:
    - None (read-only access to shared data)
    - Raises HTTPException for error conditions
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
import pandas as pd
from datetime import datetime
from auth import get_current_user

router = APIRouter()

@router.get("/pnl/transactions/{line_number}")
async def get_pnl_line_transactions(
    line_number: int,
    month: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve all transactions contributing to a specific P&L line item.
    
    Provides drill-down capability from P&L summary to individual transactions.
    Filters transactions by cost center and supplier mappings associated with
    the requested line number.
    
    Args:
        line_number (int): P&L line number to query (e.g., 9 for Marketing, 25 for Google Revenue).
        month (Optional[str]): Optional month filter in format 'YYYY-MM' (string) or integer month number.
        current_user (dict): Authenticated user object (injected by FastAPI dependency).
    
    Returns:
        Dict containing:
            - line_number: Echoed line number
            - description: Line description from mapping
            - centro_custo_filter: Cost center used for filtering
            - fornecedor_filter: Supplier/client used for filtering
            - month: Month filter applied or "all"
            - total: Sum of all transaction values (R$)
            - count: Number of transactions found
            - transactions: List of transaction dicts with:
                * date: Transaction date (YYYY-MM-DD)
                * month: Month period (YYYY-MM)
                * centro_custo: Cost center
                * fornecedor: Supplier/client name
                * descricao: Transaction description
                * valor: Transaction value (R$)
                * categoria: Account category
    
    Raises:
        HTTPException 404: If no data loaded in current_df
        HTTPException 404: If no mapping found for requested line_number
        
    Side Effects:
        - Accesses global state (current_df, current_mappings) from main module
        
    Notes:
        - Filters by cost center (case-insensitive substring match)
        - If supplier is not "Diversos", also filters by supplier (case-insensitive)
        - All matched transactions aggregated and returned
    """
    from main import current_df, current_mappings
    
    if current_df is None or current_df.empty:
        raise HTTPException(status_code=404, detail="No data loaded")
    
    # Find mapping for this line number
    line_mapping = None
    for mapping in current_mappings:
        if int(mapping.linha_pl) == line_number:
            line_mapping = mapping
            break
    
    if not line_mapping:
        raise HTTPException(
            status_code=404,
            detail=f"No mapping found for line {line_number}"
        )
    
    # Filter dataframe
    filtered_df = current_df.copy()
    
    # Apply month filter if provided
    if month:
        if '-' in str(month):  # Format: 'YYYY-MM'
            filtered_df = filtered_df[filtered_df['Mes_Competencia'] == month]
        else:  # Integer month
            filtered_df = filtered_df[filtered_df['Mes_Competencia'] == int(month)]
    
    # Apply Centro de Custo filter
    if line_mapping.centro_custo:
        filtered_df = filtered_df[
            filtered_df['Centro de Custo 1'].astype(str).str.contains(
                line_mapping.centro_custo, case=False, na=False
            )
        ]
    
    # Apply Fornecedor/Cliente filter
    if line_mapping.fornecedor_cliente and line_mapping.fornecedor_cliente != "Diversos":
        filtered_df = filtered_df[
            filtered_df['Nome do fornecedor/cliente'].astype(str).str.contains(
                line_mapping.fornecedor_cliente, case=False, na=False
            )
        ]
    
    # Build transaction list
    transactions = []
    total = 0.0
    
    for _, row in filtered_df.iterrows():
        transaction = {
            "date": row.get('Data de competência', '').strftime('%Y-%m-%d') if pd.notna(row.get('Data de competência')) else '',
            "month": str(row.get('Mes_Competencia', '')),
            "centro_custo": str(row.get('Centro de Custo 1', '')),
            "fornecedor": str(row.get('Nome do fornecedor/cliente', '')),
            "descricao": str(row.get('Descrição', '')),
            "valor": float(row.get('Valor_Num', 0)),
            "categoria": str(row.get('Plano de contas', ''))
        }
        transactions.append(transaction)
        total += transaction['valor']
    
    return {
        "line_number": line_number,
        "description": line_mapping.descricao,
        "centro_custo_filter": line_mapping.centro_custo,
        "fornecedor_filter": line_mapping.fornecedor_cliente,
        "month": month if month else "all",
        "total": total,
        "count": len(transactions),
        "transactions": transactions
    }
