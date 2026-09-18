        return render_template(

            "dashboard.html",

            total_products=total_products,
            total_orders=total_orders,
            total_customers=total_customers,
            revenue=revenue,
            low_stock=low_stock,
            failed_orders=failed_orders,

            products=products,
            orders=orders,
            customers=customers,
            reports=reports,

            products_created=products_created,
            orders_created=orders_created,
            failed_orders_metric=failed_orders_metric,
            authorized_requests=authorized_requests,
            reports_generated=reports_generated,
            report_upload_success=report_upload_success,
            report_generation_failures=report_generation_failures,

            failed_orders_alarm=failed_orders_alarm,
            low_stock_alarm=low_stock_alarm,
            unauthorized_alarm=unauthorized_alarm,
            report_alarm=report_alarm,

            health_status=health_status
        )

    finally:

        conn.close()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )