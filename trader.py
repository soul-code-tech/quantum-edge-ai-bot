def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
    try:
        print(f"📤 Отправка рыночного ордера: {side} {amount}")
        market_order = self.exchange.create_order(
            symbol=self.symbol,
            type='market',
            side=side,
            amount=amount
        )
        order_id = market_order.get('id', 'N/A')
        print(f"✅ Рыночный ордер исполнен: {order_id}")

        # Получаем цену входа из ордера (или из последней цены)
        # BingX возвращает цену исполнения в 'price'
        entry_price = market_order.get('price', None)
        if not entry_price:
            # Если цена не вернулась — берем текущую
            ticker = self.exchange.fetch_ticker(self.symbol)
            entry_price = ticker['last']

        # ✅ РАСЧЁТ TP/SL В ПРОЦЕНТАХ ОТ ЦЕНЫ ВХОДА
        if side == 'buy':
            stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
            take_profit_price = entry_price * (1 + take_profit_percent / 100)
        else:  # sell
            stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
            take_profit_price = entry_price * (1 - take_profit_percent / 100)

        print(f"📊 Цена входа: {entry_price:.2f}")
        print(f"⛔ Отправка стоп-лосса (stop_market): {stop_loss_price:.2f} ({stop_loss_percent}%)")
        print(f"🎯 Отправка тейк-профита (limit): {take_profit_price:.2f} ({take_profit_percent}%)")

        # ✅ Стоп-лосс — как stop_market, reduceOnly=True
        self.exchange.create_order(
            symbol=self.symbol,
            type='stop_market',
            side='sell' if side == 'buy' else 'buy',
            amount=amount,  # Закрываем всю позицию
            params={
                'stopPrice': stop_loss_price,
                'reduceOnly': True  # 🔥 КЛЮЧЕВОЕ!
            }
        )

        # ✅ Тейк-профит — как limit, reduceOnly=True
        self.exchange.create_order(
            symbol=self.symbol,
            type='limit',
            side='sell' if side == 'buy' else 'buy',
            amount=amount,  # Закрываем всю позицию
            price=take_profit_price,
            params={'reduceOnly': True}  # 🔥 КЛЮЧЕВОЕ!
        )

        print("✅ УСПЕХ! Все ордера отправлены (TP/SL привязаны к цене входа)")
        return market_order

    except Exception as e:
        error_str = str(e)
        if "position not exist" in error_str:
            print("❌ ОШИБКА: Позиция не найдена — возможно, ордер не исполнился или был отменён.")
        elif "Invalid order quantity" in error_str:
            print("❌ ОШИБКА: Неверный размер ордера. Убедись, что amount > 0.")
        elif "Invalid order type" in error_str:
            print("❌ ОШИБКА: Неверный тип ордера. Используй 'stop_market' и 'limit'.")
        elif "reduceOnly" in error_str:
            print("❌ ОШИБКА: reduceOnly требует существующей позиции — проверь, что ордер исполнен.")
        else:
            print(f"❌ Полная ошибка API: {type(e).__name__}: {error_str}")
        return None
