# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .sale import *


def register():
    Pool.register(
        Party,
        PartyExtraProduct,
        SaleLine,
        SetQuantitiesStart,
        SetQuantitiesStartProductProduct,
        module='sale_pos_template_extra_products', type_='model')
    Pool.register(
        SetQuantities,
        module='sale_pos_template_extra_products', type_='wizard')
