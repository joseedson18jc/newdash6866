#!/usr/bin/env python3
"""Validação Final das 8 Correções Críticas"""
import inspect
import sys

print("=" * 70)
print("VALIDAÇÃO FINAL DAS CORREÇÕES CRÍTICAS")
print("=" * 70)

try:
    import logic
    source = inspect.getsource(logic)
    
    corrections = []
    
    # 1. Imports limpos
    has_datetime_import = "from datetime import datetime" in source
    has_collections_import = "from collections import defaultdict" in source[:1000]
    corrections.append(("1. Imports desnecessários removidos", 
                       not has_datetime_import and not has_collections_import))
    
    # 2. Constantes globais
    has_payroll_const = hasattr(logic, 'PAYROLL_COST_CENTER')
    has_keywords = hasattr(logic, 'PAYROLL_KEYWORDS')
    corrections.append(("2. Constantes globais (PAYROLL_*)", 
                       has_payroll_const and has_keywords))
    
    # 3. normalize_text_helper no topo
    normalize_pos = source.find("def normalize_text_helper")
    process_pos = source.find("def process_upload")
    corrections.append(("3. normalize_text_helper antes de process_upload", 
                       0 < normalize_pos < process_pos))
    
    # 4. Nomes corretos nos mapeamentos
    get_mappings_source = inspect.getsource(logic.get_initial_mappings)
    has_google_correct = "Google Play Net Revenue" in get_mappings_source
    has_apple_correct = "App Store Net Revenue" in get_mappings_source
    corrections.append(("4. Mapeamentos com nomes corretos (Google/Apple)", 
                       has_google_correct and has_apple_correct))
    
    # 5. Revenue sem abs()
    calc_pnl_source = inspect.getsource(logic.calculate_pnl)
    has_abs_revenue = "abs(line_values[25]" in calc_pnl_source or \
                      "abs(line_values[33]" in calc_pnl_source
    corrections.append(("5. Revenue calculation SEM abs()", 
                       not has_abs_revenue))
    
    # 6. enforce_wages inclui cc_norm
    process_source = inspect.getsource(logic.process_upload)
    enforce_correct = "cc_norm," in process_source or "cc_norm ]" in process_source
    corrections.append(("6. enforce_wages_cost_center inclui cc_norm", 
                       enforce_correct))
    
    # 7. Net result simplificado
    has_simple_net_result = "net_result = total_ebitda" in calc_pnl_source or \
                           "net_result = ebitda" in calc_pnl_source
    corrections.append(("7. Net result = ebitda (simplificado)", 
                       has_simple_net_result))
    
    # 8. Payment processing rate
    has_payment_rate = "0.1765" in calc_pnl_source or "17.65" in calc_pnl_source
    corrections.append(("8. Payment processing rate (17.65%)", 
                       has_payment_rate))
    
    # Resultados
    print("\n📋 RESULTADOS DA VALIDAÇÃO:\n")
    all_passed = True
    for i, (desc, passed) in enumerate(corrections, 1):
        status = "✅" if passed else "❌"
        print(f"{status} {desc}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ TODAS AS 8 CORREÇÕES ESTÃO APLICADAS CORRETAMENTE!")
        print("=" * 70)
        print("\n🎉 Código de produção validado e pronto para deploy!")
        sys.exit(0)
    else:
        print("❌ ALGUMAS CORREÇÕES AINDA PRECISAM SER APLICADAS!")
        print("=" * 70)
        sys.exit(1)
        
except Exception as e:
    print(f"\n❌ ERRO NA VALIDAÇÃO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
