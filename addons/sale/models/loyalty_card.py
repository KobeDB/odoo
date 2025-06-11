from odoo import _, fields, models, api
from odoo.exceptions import ValidationError

import logging
from odoo.api import ondelete

_logger = logging.getLogger(__name__)

class LoyaltyCard(models.Model):
    _name = "sale.loyalty.card"
    _description = "Loyalty Card"

    _sql_constraints = [
        ('check_loyalty_points',
         'CHECK(points >= 0)',
         'The number of loyalty points can\'t be negative.'
        ),
        ('check_conversion_rate',
         'CHECK(conversion_rate > 0)',
         'The conversion rate must be greater than 0.'
        ),
        ('check_threshold',
         'CHECK(threshold > 0)',
         'The threshold must be greater than 0.'
        ),
        ('check_currency_discount',
         'CHECK(currency_discount > 0)',
         'The currency discount must be greater than 0.'
        ),
        ('check_percentage_discount',
         'CHECK(percentage_discount > 0 AND percentage_discount <= 1)',
         'The percentage discount must be greater than 0% and maximally be a 100%.'
        ),
        ('check_max_discount_amount',
         'CHECK(max_discount_amount > 0)',
         'The max_discount_amount can\'t be negative or zero.'
        ),
        (
            'unique_customer_company_card',
            'unique(partner_id, company_id)',
            'A customer can have only one loyalty card per company.'
        ),
    ]

    name = fields.Char(string="Loyalty Card Name", required=True)
    points = fields.Float(string="Loyalty Points", digits=(16, 2), default=0)
    conversion_rate = fields.Float(string="Conversion Rate", help="Points earned per unit of currency spent", digits=(16, 2), default=0.2)
    threshold = fields.Integer(string="Point Threshold", help="Points required to earn a discount.", default=100)

    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id) #the id of the currency utilised by the company
    currency_discount = fields.Monetary(string="Stores the discount to be received in currency", currency_field='currency_id', default=5)
    percentage_discount = fields.Float(string="Discount Percentage", help="Represented as all values between zero and one.", digits=(16, 2), default=0.05)
    discount_type = fields.Selection(string="Discount Type", help="Wether the discount will be in percentages or currency.", selection=[("c", "currency"), ("p", "percentage")], default="p")

    max_discount = fields.Boolean(string="Limit Discount", default=False)
    max_discount_amount = fields.Monetary(string="Maximum Discount Allowed", currency_field='currency_id', default=50)

    # links loyalty card, with customer and company pair(s).
    # customer rank defines if they can get quotations and invoices
    partner_id = fields.Many2one('res.partner', string="Partner", required=True, domain="[('customer_rank', '>', 0)]", ondelete="cascade")
    company_id = fields.Many2one('res.company', string="Company", required=True, ondelete='cascade')

    """
    Overwrite of create and write methods to ensure only one loyalty card exists per partner-company pair.
    """
    @api.model_create_multi
    def create(self, vals):
        for v in vals:
            domain = [
                ('partner_id', '=', v['partner_id']),
                ('company_id', '=', v['company_id']),
            ]
            if self.search_count(domain):
                raise ValidationError("A customer can have only one loyalty card per company.")
        return super().create(vals)

    def write(self, vals):
        for card in self:
            partner_id = vals.get('partner_id', card.partner_id.id)
            company_id = vals.get('company_id', card.company_id.id)
            domain = [
                ('partner_id', '=', partner_id),
                ('company_id', '=', company_id),
                ('id', '!=', card.id),
            ]
            if self.search_count(domain):
                raise ValidationError("A customer can have only one loyalty card per company.")
        return super().write(vals)


    # small helpers
    def discount(self):
        return self.points >= self.threshold

    # returns if the discount is limited and if it is crossed
    def maxDiscount(self, discount):
        return self.max_discount and self.max_discount_amount < discount

    # constraint checkers,
    # the same constraints as the SQL constraint,
    # this is needed since the SQL constraints are only checked upon DB commits.
    @api.constrains('points')
    def _check_points(self):
        for card in self:
            if card.points < 0:
                raise ValidationError("The number of loyalty points can't be negative.")

    @api.constrains('conversion_rate')
    def _check_conversion_rate(self):
        for card in self:
            if card.conversion_rate <= 0:
                raise ValidationError("The conversion rate can't be zero or negative.")

    @api.constrains('threshold')
    def _check_threshold(self):
        for card in self:
            if not isinstance(card.threshold, int):
                raise ValidationError("The threshold can't be a decimal number.")
            if card.threshold <= 0:
                raise ValidationError("The threshold can't be zero or negative.")

    @api.constrains('currency_discount')
    def _check_currency_discount(self):
        for card in self:
            if card.currency_discount <= 0:
                raise ValidationError("The currency_discount can't be zero or negative. (Don't be a cheap skate)")

    @api.constrains('percentage_discount')
    def _check_percentage_discount(self):
        for card in self:
            if card.percentage_discount <= 0:
                raise ValidationError("The percentage_discount can't be zero or negative.")
            if card.percentage_discount > 1:
                raise ValidationError("The percentage_discount can't be greater than 1 (100%).")

    @api.constrains('max_discount_amount')
    def _check_max_discount_amount(self):
        for card in self:
            if card.max_discount_amount <= 0:
                raise ValidationError("The max_discount_amount can't be zero or negative.")

