#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Financial Data Structure Analysis Utility.

Analyzes the structure and content of exported financial files to support
automation of the Umatch Business Plan. Generates a comprehensive report
of cost centers, categories, suppliers, and temporal distribution.

Purpose:
    - Discover unique cost centers and categories in Conta Azul exports
    - Map suppliers to cost centers for mapping configuration
    - Analyze temporal distribution of transactions
    - Export structured mapping reference in JSON format
    
Input Files (Expected):
    - /home/ubuntu/upload/00_Business_Plan_Umatch.xlsx-P&L.csv
    - /home/ubuntu/upload/00_Business_Plan_Umatch.xlsx-Assumptions.csv
    - /home/ubuntu/upload/Extratodemovimentações-2025-ExtratoFinanceiro.csv
    
Output:
    - Console report with statistics and breakdowns
    - /home/ubuntu/estrutura_mapeamento.json (structured mapping reference)
    
Side Effects:
    - Reads CSV files from /home/ubuntu/upload/
    - Writes JSON file to /home/ubuntu/
    - Prints analysis to stdout
    
Dependencies:
    - pandas: Data analysis
    - numpy: Numerical operations
    - json: Export structured data
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json

# Carregar arquivos
print("=" * 80)
print("ANÁLISE DA ESTRUTURA DOS ARQUIVOS")
print("=" * 80)

# 1. P&L
print("\n1. ESTRUTURA DO P&L")
print("-" * 80)
pl = pd.read_csv('/home/ubuntu/upload/00_Business_Plan_Umatch.xlsx-P&L.csv')
print(f"Dimensões: {pl.shape}")
print(f"Colunas: {list(pl.columns)[:5]}...")
print(f"\nPrimeiras linhas (categorias):")
print(pl.iloc[:10, :3])

# 2. Assumptions
print("\n2. ESTRUTURA DO ASSUMPTIONS")
print("-" * 80)
assumptions = pd.read_csv('/home/ubuntu/upload/00_Business_Plan_Umatch.xlsx-Assumptions.csv')
print(f"Dimensões: {assumptions.shape}")
print(f"Colunas: {list(assumptions.columns)[:5]}...")

# 3. Extrato Conta Azul
print("\n3. ESTRUTURA DO EXTRATO CONTA AZUL")
print("-" * 80)
extrato = pd.read_csv('/home/ubuntu/upload/Extratodemovimentações-2025-ExtratoFinanceiro.csv')
print(f"Dimensões: {extrato.shape}")
print(f"Colunas: {list(extrato.columns)}")
print(f"\nColunas-chave identificadas:")
print(f"  - Data de Competência: {extrato['Data de competência'].notna().sum()} registros")
print(f"  - Centro de Custo 1: {extrato['Centro de Custo 1'].notna().sum()} registros")
print(f"  - Categoria 1: {extrato['Categoria 1'].notna().sum()} registros")
print(f"  - Nome fornecedor/cliente: {extrato['Nome do fornecedor/cliente'].notna().sum()} registros")

# Análise de centros de custo únicos
print(f"\n4. CENTROS DE CUSTO ÚNICOS NO EXTRATO")
print("-" * 80)
centros = extrato['Centro de Custo 1'].dropna().unique()
print(f"Total de centros de custo: {len(centros)}")
for centro in sorted(centros):
    count = (extrato['Centro de Custo 1'] == centro).sum()
    print(f"  - {centro}: {count} registros")

# Análise de categorias únicas
print(f"\n5. CATEGORIAS ÚNICAS NO EXTRATO")
print("-" * 80)
categorias = extrato['Categoria 1'].dropna().unique()
print(f"Total de categorias: {len(categorias)}")
for cat in sorted(categorias):
    count = (extrato['Categoria 1'] == cat).sum()
    print(f"  - {cat}: {count} registros")

# Análise de fornecedores/clientes por centro de custo
print(f"\n6. FORNECEDORES/CLIENTES POR CENTRO DE CUSTO")
print("-" * 80)
for centro in sorted(centros):
    fornecedores = extrato[extrato['Centro de Custo 1'] == centro]['Nome do fornecedor/cliente'].dropna().unique()
    print(f"\n{centro} ({len(fornecedores)} fornecedores/clientes):")
    for forn in sorted(fornecedores)[:10]:  # Primeiros 10
        count = ((extrato['Centro de Custo 1'] == centro) & 
                 (extrato['Nome do fornecedor/cliente'] == forn)).sum()
        valores = extrato[(extrato['Centro de Custo 1'] == centro) & 
                         (extrato['Nome do fornecedor/cliente'] == forn)]['Valor (R$)']
        # Converter valores para numérico
        valores_num = pd.to_numeric(valores.astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce')
        total = valores_num.sum()
        print(f"  - {forn}: {count} registros, R$ {total:,.2f}")
    if len(fornecedores) > 10:
        print(f"  ... e mais {len(fornecedores) - 10} fornecedores/clientes")

# Análise temporal
print(f"\n7. ANÁLISE TEMPORAL")
print("-" * 80)
extrato['Data de competência'] = pd.to_datetime(extrato['Data de competência'], format='%d/%m/%Y', errors='coerce')
print(f"Período: {extrato['Data de competência'].min()} a {extrato['Data de competência'].max()}")
print(f"\nDistribuição mensal:")
extrato['Mes_Competencia'] = extrato['Data de competência'].dt.to_period('M')
dist_mensal = extrato.groupby('Mes_Competencia').agg({
    'Valor (R$)': ['count', 'sum']
}).round(2)
print(dist_mensal)

# Salvar análise estruturada
print(f"\n8. SALVANDO ANÁLISE ESTRUTURADA")
print("-" * 80)

# Criar mapeamento de estrutura
estrutura = {
    'centros_custo': list(centros),
    'categorias': list(categorias),
    'periodo': {
        'inicio': str(extrato['Data de competência'].min()),
        'fim': str(extrato['Data de competência'].max())
    },
    'fornecedores_por_centro': {}
}

for centro in centros:
    fornecedores = extrato[extrato['Centro de Custo 1'] == centro]['Nome do fornecedor/cliente'].dropna().unique()
    estrutura['fornecedores_por_centro'][centro] = list(fornecedores)

with open('/home/ubuntu/estrutura_mapeamento.json', 'w', encoding='utf-8') as f:
    json.dump(estrutura, f, indent=2, ensure_ascii=False)

print("Análise salva em: /home/ubuntu/estrutura_mapeamento.json")
print("\n" + "=" * 80)
print("ANÁLISE CONCLUÍDA")
print("=" * 80)
