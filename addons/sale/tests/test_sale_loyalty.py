from odoo.tests.common import TransactionCase
from odoo.fields import Command
from odoo.tests import tagged
from unittest.mock import patch
import logging

_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install', 'loyalty')
class TestSaleOrderLoyalty(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.currency = self.company.currency_id

        self.partner = self.env['res.partner'].create({
            'name': f'Test Partner {self._testMethodName}',
            'customer_rank': 1,
            'company_id': self.company.id,
        })

        self.product = self.env['product.product'].create({
            'name': f'Test Product {self._testMethodName}',
            'list_price': 100.0,
            'standard_price': 50.0,
            'currency_id': self.currency.id,
        })

        self.env['sale.loyalty.card'].search([
            ('partner_id', '=', self.partner.id),
            ('company_id', '=', self.company.id)
        ]).unlink()

        self.loyalty_card = self.env['sale.loyalty.card'].create({
            'name': 'Test Card',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'points': 2000,
            'discount_type': 'p',
            'percentage_discount': 0.1,
            'threshold': 100,
            'conversion_rate': 0.2,
            'currency_discount': 5.0,
            'max_discount': False,
            'max_discount_amount': 50,
            'currency_id': self.currency.id,
        })

        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'order_line': [
                Command.create({
                    'product_id': self.product.id,
                    'product_uom_qty': 2,
                    'price_unit': 100.0,
                })
            ]
        })

    def test_loyalty_discount_calculation(self):
        self.order._compute_amounts()
        self.assertAlmostEqual(self.order.loyalty_discount, 20.0000, 4, "Loyalty discount should be applied.")
        self.assertEqual(self.order.loyalty_points_used, 100.0, "Loyalty points used should match threshold.")

    def test_loyalty_points_awarded_calculation(self):
        self.order._compute_amounts()
        expected_points = self.order.amount_untaxed * self.loyalty_card.conversion_rate # discount already incorporated in amount untaxed
        self.assertAlmostEqual(self.order.loyalty_points, expected_points, places=2)

    def test_max_discount_enforced(self):
        self.loyalty_card.write({'max_discount': True, 'max_discount_amount': 10.0})
        self.order._compute_amounts()
        self.assertLessEqual(self.order.loyalty_discount, 10.0, "Loyalty discount should not exceed max_discount_amount.")

    def test_warning_logged_if_loyalty_card_missing(self):
        self.loyalty_card.unlink()
        with patch('odoo.addons.sale.models.sale_order._logger') as mock_logger:
            self.order._compute_amounts()
            mock_logger.warning.assert_any_call(
                f"Missing loyalty card for customer: {self.partner.name} for company: {self.company.name}"
            )

    def test_no_discount_if_threshold_not_met(self):
        self.loyalty_card.write({'points': 50})
        self.order._compute_amounts()
        self.assertEqual(self.order.loyalty_discount, 0.0, "No discount should be applied if threshold not met.")
