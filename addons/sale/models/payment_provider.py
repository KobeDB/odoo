# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

from .constants import PaymentProviderSoReferenceType

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    so_reference_type = fields.Selection(string='Communication',
        selection=[
            (str(PaymentProviderSoReferenceType.SO_NAME), 'Based on Document Reference'),
            (str(PaymentProviderSoReferenceType.PARTNER), 'Based on Customer ID')], default='so_name',
        help='You can set here the communication type that will appear on sales orders.'
             'The communication will be given to the customer when they choose the payment method.')
