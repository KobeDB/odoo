from odoo.addons.sale.tests.common import TestSaleCommonBase
from odoo.tests.common import TransactionCase

from odoo.fields import Command
from odoo.tests import tagged
from unittest.mock import patch
from parameterized import parameterized
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install', 'loyalty', 'sale')
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
    
    Points Balance: the the sum of the loyalty points gained vs spent, if it is negative then there were more spent than gained
    """
    @parameterized.expand([
        #(price, discount_type, percentage_discount, points_on_card, points_balance)
        # no points
        (0, 'p', 0.1, 20, 0),
        (0, 'c', 0.1, 20, 0),
        (0, 'p', 0.1, 2000, 0), # eligible for discount but it shouldn't be applied
        (0, 'c', 0.1, 2000, 0), # eligible for discount but it shouldn't be applied
        (2.5, 'p', 1, 20, 1),
        (2.5, 'c', 1, 20, 1),
        (2.5, 'p', 1, 2000, -100),
        (2.5, 'c', 1, 2000, -100),

        # points
        (-1, 'p', 0.1, 20, 112),
        (-1, 'c', 0.1, 20, 112),
        (-1, 'p', 0.1, 2000, 0.8),
        (-1, 'c', 0.1, 2000, 11),
    ])
    def test_loyalty_points_calculation(self, price, discount_type, percentage_discount, points_on_card, points_balance):
        if price != -1 and price >= 0:
            self.order.order_line[0].write({
                'price_unit': price,
            })

        self.loyalty_card.write({
            'discount_type': discount_type,
            'percentage_discount': percentage_discount,
            'points': points_on_card,
        })

        self.order._compute_amounts()
        self.assertAlmostEqual(self.order.loyalty_points - self.order.loyalty_points_used, points_balance, 2, "The sum of the points gained and used isn't correct.")

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
    Parameterised test, to validate correct addition and removal of points to the loyalty card.
    Used boundary value analysis to cover the different discount cases.
    """
    @parameterized.expand([
        #(discount_type, points_total, new_points_total),
        ('p', 20, 132), # out
        ('p', 99, 211), # off
        ('p', 100, 100.8), # on
        ('p', 2000, 2000.8), # in

        ('c', 20, 132),  # out
        ('c', 99, 211),  # off
        ('c', 100, 111),  # on
        ('c', 2000, 2011),  # in

    ])
    def test_loyalty_card_arithmatic(self, discount_type, points_total, new_points_total):
        self.loyalty_card.write({
            'points': points_total,
            'discount_type': discount_type,
        })
        self.order._compute_amounts()
        self.order.action_confirm()

        invoice = self.order._create_invoices()
        invoice.action_post()

        invoice.write({'payment_state': 'paid'})  # triggers _compute_loyalty_points via @depends

        self.assertTrue(invoice.loyalty_points_applied)
        self.assertTrue(self.order.loyalty_points_awarded)
        self.assertAlmostEqual(self.loyalty_card.points, new_points_total)


    # constraint tests
    def test_points(self):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'points': -20})

    @parameterized.expand([
        # (conversion_rate),
        (-20,), (-0.1,), (0,),
    ])
    def test_conversion_rate(self, conversion_rate):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'conversion_rate': conversion_rate})

    @parameterized.expand([
        # (threshold),
        (-20,), (0,),
    ])
    def test_threshold(self, threshold):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'threshold': threshold})

    @parameterized.expand([
        # (currency_discount),
        (-18.6,), (0,),
    ])
    def test_currency_discount(self, currency_discount):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'currency_discount': currency_discount})

    @parameterized.expand([
        # (percentage_discount),
        (-22,), (0,), (69,),
    ])
    def test_percentage_discount(self, percentage_discount):
        with self.assertRaises(ValidationError):
            self.loyalty_card.write({'percentage_discount': percentage_discount})

    @parameterized.expand([
        #(max_discount_amount),
        (-3.6,),(0,),
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

