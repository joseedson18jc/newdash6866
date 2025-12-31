"""
Data Models for Financial Processing System.

This module defines the data structures used throughout the financial processing
system for representing mappings, P&L items, responses, and dashboard data.
"""

from typing import Dict, List
from dataclasses import dataclass


@dataclass
class MappingItem:
    """Mapping from cost center/supplier to P&L line."""
    grupo_financeiro: str
    centro_custo: str
    fornecedor_cliente: str
    linha_pl: str
    tipo: str
    ativo: str
    observacoes: str


@dataclass
class PnLItem:
    """Single line item in P&L statement."""
    line_number: int
    description: str
    values: Dict[str, float]
    is_header: bool = False
    is_total: bool = False


@dataclass
class PnLResponse:
    """Complete P&L statement response."""
    headers: List[str]
    rows: List[PnLItem]


@dataclass
class DashboardData:
    """Dashboard metrics and visualizations data."""
    kpis: Dict[str, float]
    monthly_data: List[Dict]
    cost_structure: Dict[str, float]
