# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If, Or

__all__ = ['Template', 'Product', 'Party', 'PartyExtraProduct', 'Sale',
    'SaleExtraProduct', 'SaleLine',  'SetQuantities', 'SetQuantitiesStart']


class Template(metaclass=PoolMeta):
    __name__ = 'product.template'

    service_available_on = fields.Selection([
            ('not_available', 'Not available'),
            ('sales', 'Sales'),
            ('lines', 'Sale Lines'),
            ], 'Available On',
        states={
            'invisible': Eval('type') != 'service',
            'required': Eval('type') == 'service',
            },
        depends=['type'])

    @staticmethod
    def default_service_available_on():
        return 'not_available'


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'


class Party(metaclass=PoolMeta):
    __name__ = 'party.party'

    default_extra_services = fields.Many2Many('party-extra_product', 'party',
        'product', 'Default Extra Services',
        domain=[
            ('type', '=', 'service'),
            ('service_available_on', '=', 'sales'),
            ],
        help='These services will be added automatically to the Template '
        'Quantities wizard on Sales.')


class PartyExtraProduct(ModelSQL):
    'Party - Extra Services'
    __name__ = 'party-extra_product'

    party = fields.Many2One('party.party', 'Party', ondelete='CASCADE',
        required=True, select=True)
    product = fields.Many2One('product.product', 'Product', ondelete='RESTRICT',
        required=True, select=True)


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'
    extra_services = fields.Many2Many('sale.sale-extra_product', 'sale',
        'product', 'Extra Services',
        domain=[
            ('type', '=', 'service'),
            ('service_available_on', '=', 'sales'),
            ],
        states={
            'readonly': Eval('state') == 'done',
            },
        context={
            'company': Eval('company'),
            },
        depends=['state', 'company'])

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        if 'extra_services' not in cls.party.on_change:
            cls.party.on_change.add('extra_services')

    @fields.depends('extra_services')
    def on_change_party(self):
        super(Sale, self).on_change_party()
        if self.extra_services:
            self.extra_services = None
        if self.party and self.party.default_extra_services:
            self.extra_services = self.party.default_extra_services


class SaleExtraProduct(ModelSQL):
    'Sale - Extra Services'
    __name__ = 'sale.sale-extra_product'
    sale = fields.Many2One('sale.sale', 'Sale', ondelete='CASCADE',
        required=True, select=True)
    product = fields.Many2One('product.product', 'Product', ondelete='RESTRICT',
        required=True, select=True)


class SaleLine(metaclass=PoolMeta):
    __name__ = 'sale.line'
    template_extra_parent = fields.Many2One('sale.line', 'Parent', domain=[
            ('type', '=', 'line'),
            ('template', '!=', None),
            ('product', '=', None),
            ('template_parent', '=', None),
            ('template_extra_parent', '=', None),
            ], ondelete='CASCADE')
    template_extra_childs = fields.One2Many('sale.line',
        'template_extra_parent', 'Childs', domain=[
            ('type', '=', 'line'),
            ('template', '=', None),
            ('product', '!=', None),
            ('product.type', '=', 'service'),
            ('product.service_available_on', '=', 'lines'),
            ('template_parent', '=', None),
            ])

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        cls.type.states['readonly'] = Or(cls.type.states['readonly'],
            Bool(Eval('template_extra_parent')),
            Bool(Eval('template_extra_childs')))
        cls.type.depends |= {'template_extra_parent', 'template_extra_childs'}

        cls.product.domain.insert(0,
            If(Bool(Eval('template_extra_parent', 0)),
                ('type', '=', 'service'),
                ()))
        cls.product.depends.add('template_extra_parent')

        cls.template.context = {'company': Eval('company')}
        cls.template.depends.add('company')

    def update_template_line_quantity(self):
        old_quantity = self.quantity
        super(SaleLine, self).update_template_line_quantity()
        for extra_child_line in self.template_extra_childs:
            old_unit_price = extra_child_line.unit_price
            if (extra_child_line.on_change_quantity().unit_price
                    == old_unit_price):
                # The user didn't changed the unit price
                old_unit_price = None
            if extra_child_line.quantity == old_quantity:
                extra_child_line.quantity = self.quantity
            extra_child_line.on_change_product()

            if old_unit_price is not None:
                extra_child_line.unit_price = old_unit_price
            extra_child_line.save()

    def update_sequence(self, next_sequence):
        if self.template_extra_parent:
            return next_sequence
        return super(SaleLine, self).update_sequence(next_sequence)

    def update_child_lines_sequence(self, next_sequence):
        next_sequence = super(SaleLine, self).update_child_lines_sequence(
                next_sequence)
        for child_line in self.template_extra_childs:
            if child_line.sequence != next_sequence:
                child_line.sequence = next_sequence
                child_line.save()
            next_sequence += 1
        return next_sequence

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['template_extra_childs'] = None
        new_lines = super(SaleLine, cls).copy(lines, default=default)

        def sortfunc(a):
            return (a.template.id if a.template else 0,
                a.product.id if a.product else 0)

        lines = sorted(lines, key=sortfunc)
        new_lines = sorted(new_lines, key=sortfunc)
        new_line_by_line = dict((l, nl) for l, nl in zip(lines, new_lines))
        for new_line in new_lines:
            parent_line = new_line.template_extra_parent
            if parent_line and parent_line in lines:
                new_line.template_extra_parent = (
                    new_line_by_line[parent_line].id)
                new_line.save()
        return new_lines


class SetQuantitiesStart(metaclass=PoolMeta):
    __name__ = 'sale_pos.set_quantities.start'

    template_line_template = fields.Many2One('product.template', 'Template',
        readonly=True)
    extra_products = fields.Many2Many('product.product', None, None,
        'Extra Products',
        domain=[
            ('template', '!=', Eval('template_line_template')),
            ('salable', '=', True),
            ('type', '=', 'service'),
            ('service_available_on', '=', 'lines'),
            ],
        depends=['template_line_template'])


class SetQuantities(metaclass=PoolMeta):
    __name__ = 'sale_pos.set_quantities'

    def default_start(self, fields):
        SaleLine = Pool().get('sale.line')

        res = super(SetQuantities, self).default_start(fields)
        if not res:
            return res

        template_line = SaleLine(res['template_line'])
        if (template_line.template_extra_childs or
                template_line.template_childs):
            res['extra_products'] = list(set(l.product.id
                for l in template_line.template_extra_childs))
        res['template_line_template'] = template_line.template.id
        return res

    def transition_set_(self, *args, **kwargs):
        pool = Pool()
        SaleLine = pool.get('sale.line')

        old_quantity = self.start.template_line.quantity

        res = super(SetQuantities, self).transition_set_(*args, **kwargs)
        template_line = self.start.template_line
        if not self.start.extra_products:
            if template_line.template_extra_childs:
                SaleLine.delete(template_line.template_extra_childs)
            return res

        child_line_by_product = dict((l.product, l)
            for l in template_line.template_extra_childs)
        lines_to_delete = list(template_line.template_extra_childs[:])

        for extra_product in self.start.extra_products:
            line = child_line_by_product.get(extra_product)

            if line:
                lines_to_delete.remove(line)

                old_unit_price = line.unit_price
                if line.on_change_quantity().unit_price == old_unit_price:
                    # The user didn't changed the unit price
                    old_unit_price = None
                if line.quantity == old_quantity:
                    line.quantity = template_line.quantity
                line.on_change_quantity()
                if old_unit_price is not None:
                    line.unit_price = old_unit_price
            else:
                line = SaleLine()
                line.sale = template_line.sale
                line.sequence = template_line.sequence
                line.template_parent = None
                line.template_extra_parent = template_line
                line.template = None
                line.product = extra_product
                line.unit = None
                line.description = None
                line.quantity = template_line.quantity
                line.on_change_product()
                line.on_change_quantity()
            line.save()

        if lines_to_delete:
            SaleLine.delete(lines_to_delete)
        return res
