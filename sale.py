# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import Model, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If, Or

__all__ = ['Party', 'PartyExtraProduct', 'SaleLine',
    'SetQuantities', 'SetQuantitiesStart', 'SetQuantitiesStartProductProduct']
__metaclass__ = PoolMeta


class Party:
    __name__ = 'party.party'

    default_extra_services = fields.Many2Many('party-extra_product', 'party',
        'product', 'Default Extra Services', domain=[
            ('type', '=', 'service'),
            ],
        help='These services will be added automatically to the Template '
        'Quantities wizard on Sales.')


class PartyExtraProduct(ModelSQL):
    'Party - Extra Services'
    __name__ = 'party-extra_product'

    party = fields.Many2One('party.party', 'Party', ondelete='CASCADE',
        required=True, select=True)
    product = fields.Many2One('product.product', 'Product', ondelete='CASCADE',
        required=True, select=True)


class SaleLine:
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
            ('template_parent', '=', None),
            ])

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        cls.type.states['readonly'] = Or(cls.type.states['readonly'],
            Bool(Eval('template_extra_parent')),
            Bool(Eval('template_extra_childs')))
        cls.type.depends += ['template_extra_parent', 'template_extra_childs']

        cls.product.domain.insert(0,
            If(Bool(Eval('template_extra_parent', 0)),
                ('type', '=', 'service'),
                ()))
        cls.product.depends.append('template_extra_parent')

        cls.quantity.states['readonly'] = Or(cls.quantity.states['readonly'],
            Bool(Eval('template_extra_parent', 0)))
        cls.quantity.depends.append('template_extra_parent')

    def update_template_line_quantity(self):
        super(SaleLine, self).update_template_line_quantity()
        for extra_child_line in self.template_extra_childs:
            extra_child_line.quantity = self.quantity
            ocp_res = extra_child_line.on_change_product()
            for f, v in ocp_res.iteritems():
                setattr(extra_child_line, f, v)
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

        new_line_by_line = dict((l, nl) for l, nl in zip(lines, new_lines))
        for new_line in new_lines:
            parent_line = new_line.template_extra_parent
            if parent_line and parent_line in lines:
                new_line.template_extra_parent = (
                    new_line_by_line[parent_line].id)
                new_line.save()
        return new_lines


class SetQuantitiesStart:
    __name__ = 'sale_pos.set_quantities.start'

    template_line_template = fields.Many2One('product.template', 'Template',
        readonly=True)
    extra_products = fields.Many2Many(
        'sale_pos.set_quantities.start-product.product', 'start', 'product',
        'Extra Products', domain=[
            ('template', '!=', Eval('template_line_template')),
            ('salable', '=', True),
            ('type', '=', 'service'),
            ], depends=['template_line_template'])


class SetQuantitiesStartProductProduct(Model):
    'Set Quantities Start - Product Product'
    __name__ = 'sale_pos.set_quantities.start-product.product'

    start = fields.Many2One('sale_pos.set_quantities.start',
        'Set Quantities Start', ondelete='CASCADE', required=True, select=True)
    product = fields.Many2One('product.product', 'Set Quantities Start',
        ondelete='CASCADE', required=True, select=True)


class SetQuantities:
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
        else:
            res['extra_products'] = [p.id
                for p in template_line.sale.party.default_extra_services]
        res['template_line_template'] = template_line.template.id
        return res

    def transition_set_(self):
        pool = Pool()
        SaleLine = pool.get('sale.line')

        res = super(SetQuantities, self).transition_set_()

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
                ocp_res = line.on_change_product()
                for f, v in ocp_res.iteritems():
                    setattr(line, f, v)

            line.quantity = template_line.quantity
            ocp_res = line.on_change_quantity()
            for f, v in ocp_res.iteritems():
                setattr(line, f, v)
            line.save()

        if lines_to_delete:
            SaleLine.delete(lines_to_delete)
        return res
