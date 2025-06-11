from odoo.addons.sale.tests.common import TestSaleCommonBase
from odoo.tests.common import TransactionCase

from odoo.fields import Command
from odoo.tests import tagged
from unittest.mock import patch
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install', 'loyalty')
class TestSaleOrderLoyalty(TestSaleCommonBase):
    def setUp(self):
        super().setUp()
        self.test_data = self.setup_sale_configuration_for_company(self.env.company)

        self.company = self.env.company
        self.currency = self.company.currency_id

        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'customer_rank': 1,
            'company_id': self.company.id,
        })

        self.product = self.test_data['product_order_cost']

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
                    'price_unit': self.product.list_price,
                })
            ]
        })

    # TODO add tests for checking if the points are awarded and subtracted to the card after payment

    """
    Checks if the discounts get applied, for both currency and percentage discount types.
    """
    def test_discount(self):
        self.order._compute_amounts()
        self.assertAlmostEqual(self.order.loyalty_discount, 56, 2, "Loyalty discount should be applied.")
        self.assertEqual(self.order.loyalty_points_used, self.loyalty_card.threshold,"Loyalty points used should match threshold.")

        self.loyalty_card.write({
            'discount_type': 'c',
        })
        self.order._compute_amounts()
        self.assertEqual(self.order.loyalty_discount, self.loyalty_card.currency_discount, "Loyalty discount should be applied.")
        self.assertEqual(self.order.loyalty_points_used, self.loyalty_card.threshold, "Loyalty points used should match threshold.")

    """
    Don't provide discount in case of insufficient points total
    """
    def test_insufficient_points(self):
        self.loyalty_card.write({
            'points':20,
        })
        self.order._compute_amounts()
        self.assertAlmostEqual(self.order.loyalty_discount, 0, 2, "Loyalty discount should be applied in case of insufficient points.")
        self.assertEqual(self.order.loyalty_points_used, 0,"No Loyalty points should used in case of insufficient points.")

    """
    Validate loyalty points to be received with no discount applied
    """
    def test_loyalty_points_calculation(self):
        self.loyalty_card.write({
            'points': 20,
        })
        self.order._loyalty_points()
        self.assertAlmostEqual(self.order.loyalty_points, 112)

    """
    Verify points getting added to the card without any discount
    """
    def test_points_addition_to_card(self):
        self.loyalty_card.write({
            'points': 20,
        })
        self.order._compute_amounts()
        self.order.action_confirm()

        invoice = self.order._create_invoices()
        invoice.action_post()

        invoice.write({'payment_state': 'paid'})  # triggers _compute_loyalty_points via @depends

        # self.card.invalidate_cache()  # make sure we see latest DB values
        self.assertTrue(invoice.loyalty_points_applied)
        self.assertTrue(self.order.loyalty_points_awarded)
        self.assertAlmostEqual(self.loyalty_card.points, 132) # 20 + 112

    """
    Validate loyalty points to be received with a discount applied
    """
    def test_loyalty_points_calculation_with_discount(self):
        self.order._compute_amounts()
        self.assertAlmostEqual(self.order.loyalty_points, 100.8)


    """
    Verify points getting added and removed to the card with a discount
    """
    def test_points_addition_to_card_with_discount(self):
        self.order._compute_amounts()
        self.order.action_confirm()

        invoice = self.order._create_invoices()
        invoice.action_post()

        invoice.write({'payment_state': 'paid'})  # triggers _compute_loyalty_points via @depends

        # self.card.invalidate_cache()  # make sure we see latest DB values
        self.assertTrue(invoice.loyalty_points_applied)
        self.assertTrue(self.order.loyalty_points_awarded)
        self.assertAlmostEqual(self.loyalty_card.points, 2000 + 100.8 - self.loyalty_card.threshold) # 2000 + 100.8 - threshold (100)

    """
    Validate maximum discount limit
    """
    def test_max_discount(self):
        self.loyalty_card.write({
            'max_discount': True,
        })
        self.order._compute_amounts()
        self.assertEqual(self.order.loyalty_discount, 50, "The discount shouldn't exceed the maximum discount allowed")
        self.assertEqual(self.order.loyalty_points_used, self.loyalty_card.threshold,"Loyalty points used should match threshold.")


    def test_loyalty_card_missing(self):
        self.loyalty_card.unlink()
        with patch('odoo.addons.sale.models.sale_order._logger') as mock_logger:
            self.order._compute_amounts()
            mock_logger.warning.assert_any_call(
                f"Missing loyalty card for customer: {self.partner.name} for company: {self.company.name}"
            )



    # constraint tests
    def test_points(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'points': -20})

    def test_conversion_rate(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'conversion_rate': -0.1})

        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'conversion_rate': 0})

    def test_threshold(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'threshold': -20})

        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'threshold': 0})

        # seemingly useless as floats just get converted to ints
        # with self.assertRaises(ValidationError):
        #     self.loyalty_card.write({'threshold': 4.20})

    def test_currency_discount(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'currency_discount': -18.6})

        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'currency_discount': 0})

    def test_percentage_discount(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'percentage_discount': -22})

        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'percentage_discount': 0})

    def test_max_discount_amount(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'max_discount_amount': -3.6})

        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'max_discount_amount': 0})

    def test_unique_cards(self):
        with self.assertRaises(ValidationError):
            self.env['sale.loyalty.card'].create({
                'name': 'Duplicate Card',
                'points': 100,
                'partner_id': self.loyalty_card.partner_id.id,
                'company_id': self.loyalty_card.company_id.id,
                'currency_id': self.loyalty_card.currency_id.id,
            })

