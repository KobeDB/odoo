from odoo.addons.sale.tests.common import TestSaleCommonBase
from odoo.tests.common import TransactionCase

from odoo.fields import Command
from odoo.tests import tagged
from unittest.mock import patch
from parameterized import parameterized
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


    """
    Parameterised test, checking if discounts are applied only when necessary, for both discount types.  
    With variants determined by boundary value analysis.
    """
    @parameterized.expand([
        # (points, discount_type, discount_applied, discount)
        # percentage discounts
        (20, 'p', False, 0),  # out
        (99, 'p', False, 0),  # off
        (100, 'p', True, 56),  # on
        (420, 'p', True, 56),  # in

        # currency discounts
        (20, 'c', False, 0),  # out
        (99, 'c', False, 0),  # off
        (100, 'c', True, 5),  # on
        (420, 'c', True, 5),  # in
    ])
    def test_discount(self, points, discount_type, discount_applied, discount):
        self.loyalty_card.write({
            'discount_type': discount_type,
            'points': points,
        })
        self.order._compute_amounts()
        self.assertEqual(self.order.loyalty_discount, discount, "The loyalty discount doesn't match")
        if discount_applied:
            self.assertEqual(self.order.loyalty_points_used, self.loyalty_card.threshold, "Loyalty points used should match threshold.")
        else:
            self.assertEqual(self.order.loyalty_points_used, 0, "Loyalty points used should be zero, when no discount was applied.")

    """
    Parameterised test, checking if the number of loyalty points a customer should receive after a purchase is correct.
    For both discount types and various cases, most importantly when the order's total price is zero.
    """
    @parameterized.expand([
        #(price, discount_type, percentage_discount, points_total, new_points_total)
        # no points
        (0, 'p', 0.1, 20, 20),
        (0, 'c', 0.1, 20, 20),
        (0, 'p', 0.1, 2000, 2000), # eligible for discount but it shouldn't be applied
        (0, 'c', 0.1, 2000, 2000), # eligible for discount but it shouldn't be applied
        (2.5, 'p', 1, 20, 21),
        (2.5, 'c', 1, 20, 21),
        (2.5, 'p', 1, 2000, 1900),
        (2.5, 'c', 1, 2000, 1900),

        # points
        (-1, 'p', 0.1, 20, 132),
        (-1, 'c', 0.1, 20, 132),
        (-1, 'p', 0.1, 2000, 1900+100.8),
        (-1, 'c', 0.1, 2000, 1900+111),
    ])
    def test_loyalty_points_calculation(self, price, discount_type, percentage_discount, points_total, new_points_total):
        if price != -1 and price >= 0:
            self.order.order_line[0].write({
                'price_unit': price,
            })

        self.loyalty_card.write({
            'discount_type': discount_type,
            'percentage_discount': percentage_discount,
            'points': points_total,
        })

        self.order._compute_amounts()
        self.assertAlmostEqual(points_total + self.order.loyalty_points - self.order.loyalty_points_used, new_points_total, 2, "Points should be equal to total points.")

    """
    Parameterised test, to validate correct application of the discount limit. With scuffy boundary value analysis.
    """
    @parameterized.expand([
        #(max_discount_amount, discount_type, currency_discount, actual_discount),
        # percentage discount
        (100, 'p', 5, 56), # in
        (56, 'p', 5, 56), # on
        (55, 'p', 5, 55),  # off
        (50, 'p', 5, 50),  # out

        # currency discount
        (100, 'c', 5, 5), # in
        (100, 'c', 100, 100), # on
        (50, 'c', 51, 50),  # off
        (50, 'c', 100, 50),  # out

    ])
    def test_max_discount(self, max_discount_amount, discount_type, currency_discount, actual_discount):
        self.loyalty_card.write({
            'max_discount': True,
            'max_discount_amount': max_discount_amount,
            'discount_type': discount_type,
            'currency_discount': currency_discount,
        })
        self.order._compute_amounts()
        self.assertEqual(self.order.loyalty_discount, actual_discount, "The discount doesn't match the expected discount.")
        self.assertEqual(self.order.loyalty_points_used, self.loyalty_card.threshold,"Loyalty points used should match threshold.") # discount is always applied

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
        self.assertAlmostEqual(self.loyalty_card.points, 20 + 112)

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

    # constraint tests
    def test_points(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'points': -20})

    @parameterized.expand([
        # (conversion_rate),
        (-20), (-0.1), (0),
    ])
    def test_conversion_rate(self, conversion_rate):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'conversion_rate': conversion_rate})

    @parameterized.expand([
        # (threshold),
        (-20), (0),
    ])
    def test_threshold(self, threshold):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'threshold': threshold})

    @parameterized.expand([
        # (currency_discount),
        (-18.6), (0),
    ])
    def test_currency_discount(self, currency_discount):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'currency_discount': currency_discount})

    @parameterized.expand([
        # (percentage_discount),
        (-22), (0), (69),
    ])
    def test_percentage_discount(self, percentage_discount):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'percentage_discount': percentage_discount})

    @parameterized.expand([
        #(max_discount_amount),
        (-3.6),(0),
    ])
    def test_max_discount_amount(self, max_discount_amount):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'max_discount_amount': max_discount_amount})

    def test_unique_cards(self):
        with self.assertRaises(ValidationError):
            self.env['sale.loyalty.card'].create({
                'name': 'Duplicate Card',
                'points': 100,
                'partner_id': self.loyalty_card.partner_id.id,
                'company_id': self.loyalty_card.company_id.id,
                'currency_id': self.loyalty_card.currency_id.id,
            })

