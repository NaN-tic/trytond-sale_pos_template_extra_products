# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import sale


def register():
    Pool.register(
        sale.Template,
        sale.Product,
        sale.Party,
        sale.PartyExtraProduct,
        sale.Sale,
        sale.SaleExtraProduct,
        sale.SaleLine,
        sale.SetQuantitiesStart,
        module='sale_pos_template_extra_products', type_='model')
    Pool.register(
        sale.SetQuantities,
        module='sale_pos_template_extra_products', type_='wizard')
