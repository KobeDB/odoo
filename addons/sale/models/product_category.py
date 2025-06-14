from odoo import models, fields

from .constants import *

class ProductCategory(models.Model):
    _inherit = "product.category"

    property_account_downpayment_categ_id = fields.Many2one(
        comodel_name='account.account',
        company_dependent=True,
        string="Downpayment Account",
        domain=[
            ('deprecated', '=', False),
            ('account_type', 'not in', (str(AccountAccountType.ASSET_RECEIVABLE), str(AccountAccountType.LIABILITY_PAYABLE), str(AccountAccountType.ASSET_CASH), str(AccountAccountType.LIABILITY_CREDIT_CARD), str(AccountAccountType.OFF_BALANCE)))
        ],
        help="This account will be used on Downpayment invoices.",
        tracking=True,
    )
