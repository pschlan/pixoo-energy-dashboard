import datetime
import time
import homeassistant_api
import tibber
import iso8601
import pytz

from pixoo import Pixoo, SimulatorConfig


HASS_URL = 'http://192.168.1.117:8123/api/'
HASS_API_TOKEN = 'TODO'
TIBBER_API_TOKEN = 'TODO'
PIXOO_ADDRESS = '192.168.1.78'


def update_state(hass_client, state, key, entity):
  try:
    value = hass_client.get_entity(entity_id=entity).get_state().state
    if value == 'unavailable':
      state[key] = None
    else:
      state[key] = float(value)
  except Exception as e:
    print('Failed to retrieve entity: {}'.format(entity), e)


def short_format(val, mul = None):
  if val is None:
    return '0'
  if mul is not None:
    val *= mul
  if val > 999:
    return '{:.2f}k'.format(val / 1000)
  return '{:.0f}'.format(val)


def run():
  state = {
    'price_tibber': None,
    'p_solar': None,
    'e_solar': None,
    'p_floor2': None,
    'p_floor1': None,
    'e_floor2': None,
    'e_floor1': None,
    'price_prediction': []
  }

  tibber_account = None

  last_tibber_update = None

  with homeassistant_api.Client(
      HASS_URL,
      HASS_API_TOKEN,
      cache_session=False
  ) as hass_client:
    pixoo = Pixoo(PIXOO_ADDRESS, refresh_connection_automatically=True)#, simulated=True, simulation_config=SimulatorConfig(4))

    white = (255, 255, 255)
    green = (99, 199, 77)
    darkblue = (0, 0, 139)

    while True:
      now = datetime.datetime.now(pytz.utc)

      if last_tibber_update is None or (time.time() - last_tibber_update) > 60:
        print('Refreshing tibber data!')

        try:
          if not tibber_account:
            tibber_account = tibber.Account(TIBBER_API_TOKEN)

          tibber_account.update()

          tibber_home = None
          for home in tibber_account.homes:
            if home.app_nickname == 'MTA Unten':
              tibber_home = home
              break
          prices = tibber_home.current_subscription.price_info.today + tibber_home.current_subscription.price_info.tomorrow

          cur_price = tibber_home.current_subscription.price_info.current
          state['price_prediction'] = [
            {
              'value': cur_price.total,
              'level': cur_price.level,
              'cur': True
            }
          ]

          for price in prices:
            price_date = iso8601.parse_date(price.starts_at)
            if price_date >= now:
              state['price_prediction'].append({
                'value': price.total,
                'level': price.level,
                'cur': False
              })
              if len(state['price_prediction']) >= 12:
                break

        except Exception as e:
          print('Tibber API error:', e)

        last_tibber_update = time.time()

      update_state(hass_client, state, 'price_tibber', 'sensor.electricity_price_mta_unten')
      update_state(hass_client, state, 'p_solar', 'sensor.balkon_p_ac')
      update_state(hass_client, state, 'p_floor1', 'sensor.power_mta_unten')
      update_state(hass_client, state, 'p_floor2', 'sensor.power_mta_oben')
      update_state(hass_client, state, 'e_solar', 'sensor.balkon_yieldday')
      update_state(hass_client, state, 'e_floor1', 'sensor.accumulated_consumption_mta_unten')
      update_state(hass_client, state, 'e_floor2', 'sensor.accumulated_consumption_mta_oben')

      print('update {}'.format(state))

      pixoo.clear()

      pixoo.draw_text('  {} {}'.format(
        'W'.rjust(6, ' '),
        'Wh'.rjust(6, ' ')
      ), (2, 2 + 7 * 0), white)

      pixoo.draw_text('>', (2, 2 + 7 * 1), white)
      pixoo.draw_text('  {} {}'.format(
        short_format(state['p_solar']).rjust(6, ' '),
        short_format(state['e_solar']).rjust(6, ' ')
      ), (2, 2 + 7 * 1), green)

      pixoo.draw_text('2', (2, 2 + 7 * 2), white)
      pixoo.draw_text('  {} {}'.format(
        short_format(state['p_floor2']).rjust(6, ' '),
        short_format(state['e_floor2'], 1000).rjust(6, ' ')
      ), (2, 2 + 7 * 2), green)

      pixoo.draw_text('1', (2, 2 + 7 * 3), white)
      pixoo.draw_text('  {} {}'.format(
        short_format(state['p_floor1']).rjust(6, ' '),
        short_format(state['e_floor1'], 1000).rjust(6, ' ')
      ), (2, 2 + 7 * 3), green)

      pixoo.draw_text(datetime.datetime.now().strftime('%H:%M'), (64 - 2 - 4 * 5, 64-7), green)

      graph_pos = (2, 2 + 7 * 4 + 1)
      graph_size = (60, 22)
      graph_item_width = 5

      pixoo.draw_filled_rectangle((graph_pos[0] - 2, graph_pos[1] - 1), (graph_pos[0] + graph_size[0] + 2, graph_pos[1] + graph_size[1] + 1), darkblue)

      if len(state['price_prediction']) > 0:
        price_min = min([x['value'] for x in state['price_prediction']])
        price_max = max([x['value'] for x in state['price_prediction']])
        price_scale = graph_size[1] / (price_max - price_min)

        # https://www.color-hex.com/color-palette/35021
        colors = {
          'VERY_CHEAP': (45, 201, 55),
          'CHEAP': (153, 193, 64),
          'NORMAL': (231, 180, 22),
          'EXPENSIVE': (219, 123, 43),
          'VERY_EXPENSIVE': (204, 50, 50)
        }

        prev_line_end = None
        for x, price in enumerate(state['price_prediction']):
          line_start = (graph_pos[0] + x * graph_item_width, round(graph_pos[1] + graph_size[1] - (price['value'] - price_min) * price_scale))
          line_end = (line_start[0] + graph_item_width, line_start[1])
          color = colors[price['level']]

          pixoo.draw_line(line_start, line_end, color)

          if price['cur']:
            pixoo.draw_text('{:.1f} ct'.format(price['value'] * 100.), (2, 64-7), color)

          if prev_line_end is not None:
            if line_start[1] != prev_line_end[1]:
              pixoo.draw_line((prev_line_end[0], prev_line_end[1]), line_start, color)

          prev_line_end = line_end

      pixoo.push()

      time.sleep(2)


def main():
  while True:
    try:
      run()
    except Exception as e:
      print('Top level error:', e)
      time.sleep(10)

main()


