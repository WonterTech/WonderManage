"""Money maths for factures and bons de livraison (exact Decimal, 3 decimals like the dinar's millimes)."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MILLIME = Decimal("0.001")
VAT_RATES = [Decimal("19"), Decimal("13"), Decimal("7"), Decimal("0")]


def r3(value):
    return Decimal(value).quantize(MILLIME, rounding=ROUND_HALF_UP)


def line_figures(quantity, unit_price, discount_pct, vat_rate):
    """(total HT after discount, VAT amount, total TTC) of one line."""
    gross = Decimal(quantity or 0) * Decimal(unit_price or 0)
    ht = r3(gross * (HUNDRED - Decimal(discount_pct or 0)) / HUNDRED)
    vat = r3(ht * Decimal(vat_rate or 0) / HUNDRED)
    return ht, vat, ht + vat


def document_totals(document, lines=None):
    """Everything the document page and the printout need."""
    rows, total_ht, vat_groups = [], ZERO, {}
    for line in (document.lines.all() if lines is None else lines):
        ht, vat, ttc = line_figures(line.quantity, line.unit_price, line.discount_pct, line.vat_rate)
        rows.append({"line": line, "ht": ht, "vat": vat, "ttc": ttc})
        total_ht += ht
        base, amount = vat_groups.get(line.vat_rate, (ZERO, ZERO))
        vat_groups[line.vat_rate] = (base + ht, amount + vat)
    total_vat = sum((a for _b, a in vat_groups.values()), ZERO)
    subtotal = total_ht + total_vat                      # HT + TVA
    stamp = r3(document.stamp_duty or 0)
    withholding = r3(subtotal * Decimal(document.withholding_rate or 0) / HUNDRED)
    return {
        "rows": rows,
        "total_ht": total_ht,
        "vat_groups": [{"rate": rate, "base": b, "amount": a} for rate, (b, a) in sorted(vat_groups.items(), reverse=True)],
        "total_vat": total_vat,
        "stamp": stamp,
        "total_ttc": subtotal + stamp,
        "withholding": withholding,
        "net": subtotal + stamp - withholding,
    }
