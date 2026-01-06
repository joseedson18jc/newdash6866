# Code Review Response

## Review Comments Addressed

### Comment 1: PAYROLL_KEYWORDS Duplicate Variations
**Location:** logic.py, lines 79-92

**Reviewer Comment:**
> The PAYROLL_KEYWORDS list contains duplicate variations that would produce identical normalized results. For example, 'salario' and 'salário' both normalize to the same string.

**Response:**
This is intentional and matches the reference implementation in `logic_CORRECTED.py`. The duplicates serve several purposes:

1. **Maintainability:** Keeping original variations visible in source code makes it clear which keywords are being matched, even if they normalize to the same value
2. **Documentation:** Shows the different forms users might enter in Conta Azul
3. **Consistency:** Matches the validated reference implementation exactly

The normalization happens at list creation time (line 90: `normalize_text_helper(k)`), so there's no runtime performance impact. The final list contains 12 unique normalized keywords.

**Action:** No change needed - behavior is correct and intentional.

---

### Comment 2: Inconsistent use of abs() - COGS vs Revenue
**Location:** logic.py, line 703

**Reviewer Comment:**
> Revenue calculations preserve sign for refunds (lines 680-682) but COGS calculation still uses abs(). Consider whether COGS should also preserve sign for consistency.

**Response:**
This is correct and intentional. The different treatment is by design:

**Revenue (NO abs()):**
- Lines 680-682: Preserves sign
- Reason: Refunds/chargebacks should REDUCE revenue
- Example: $1000 revenue - $200 refund = $800 net revenue

**COGS (WITH abs()):**
- Line 703: Uses abs()
- Reason: COGS are always costs (negative values in accounting)
- Example: Web services costs are expenses, should always be positive in P&L display

This matches the reference implementation in `logic_CORRECTED.py` line 535:
```python
# 3. COGS
cogs_sum = sum(abs(line_values[i].get(m, 0.0)) for i in range(43, 49))
```

**Action:** No change needed - behavior is correct per financial requirements.

---

## Summary

Both code review comments address intentional design decisions that:
1. Match the validated reference implementation (`logic_CORRECTED.py`)
2. Follow proper financial accounting principles
3. Are documented in the business plan

No changes are required. The corrections are working as designed.
