from odoo import _, fields, models

import logging
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
         'The percentage discount must be greater than 0%.'
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
    max_discount_amount = fields.Integer(string="Maximum Discount Allowed", default=50)

    # links loyalty card, with customer and company pair(s).
    partner_id = fields.Many2one('res.partner', string="Partner", required=True, domain="[('customer_rank', '>', 0)]",)
    company_id = fields.Many2one('res.company', string="Company", required=True)

    def discount(self):
        return self.points >= self.threshold

    #check if the discount is limited and if it is crossed
    def maxDiscount(self, discount):
        return self.max_discount and self.max_discount_amount < discount