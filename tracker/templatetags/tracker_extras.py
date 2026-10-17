from django import template

from ..inventory import fmt_money, fmt_qty

register = template.Library()
register.filter("qty", fmt_qty)
register.filter("money", fmt_money)
