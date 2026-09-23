<?php
/**
 * POST /net-gain/v1/shows/{id}/index-snapshot - written by tick.py after
 * fetching and parsing a show's Google Sheet index tracker
 * (pipeline/edtech_index.py). Stores the whole constituent list as one JSON
 * blob (ng_index_snapshot), replaced wholesale on every successful fetch -
 * deliberately no per-ticker WordPress records to reconcile, so
 * constituents can be added or removed in the sheet at any time with no
 * corresponding code or data-model change needed here (the user's own
 * stated requirement, 2026-09-21: "ensure your code anticipates securities
 * coming and going from the Sheet").
 *
 * A failed fetch is never routed through this endpoint at all - tick.py
 * only calls this on success, and leaves the previous ng_index_snapshot in
 * place on failure (see process_index_refresh() in tick.py) so a down or
 * misconfigured sheet degrades to "showing yesterday's real numbers", never
 * to a blank or broken page.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Index_Snapshot {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/index-snapshot',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'store' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
				},
			)
		);
	}

	public function store( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$show    = get_post( $show_id );
		if ( ! $show || Net_Gain_CPT_Show::POST_TYPE !== $show->post_type ) {
			return new WP_Error( 'ng_show_not_found', 'Show not found.', array( 'status' => 404 ) );
		}

		$body = $request->get_json_params();
		if ( empty( $body['constituents'] ) || ! is_array( $body['constituents'] ) ) {
			return new WP_Error(
				'ng_index_empty',
				'Refusing to store an index snapshot with no constituents.',
				array( 'status' => 400 )
			);
		}

		$constituents = array();
		foreach ( $body['constituents'] as $row ) {
			if ( empty( $row['ticker'] ) ) {
				continue; // Mirrors edtech_index.py's own skip of blank/tickerless rows.
			}
			$constituents[] = array(
				'ticker'             => sanitize_text_field( $row['ticker'] ),
				'exchange'           => sanitize_text_field( $row['exchange'] ?? '' ),
				'company'            => sanitize_text_field( $row['company'] ?? '' ),
				'country'            => sanitize_text_field( $row['country'] ?? '' ),
				'segment'            => sanitize_text_field( $row['segment'] ?? '' ),
				'price'              => isset( $row['price'] ) && null !== $row['price'] ? (float) $row['price'] : null,
				'day_change_percent' => isset( $row['day_change_percent'] ) && null !== $row['day_change_percent'] ? (float) $row['day_change_percent'] : null,
				'position_value'     => isset( $row['position_value'] ) && null !== $row['position_value'] ? (float) $row['position_value'] : null,
				'ytd_change_percent' => isset( $row['ytd_change_percent'] ) && null !== $row['ytd_change_percent'] ? (float) $row['ytd_change_percent'] : null,
			);
		}

		if ( empty( $constituents ) ) {
			return new WP_Error(
				'ng_index_empty',
				'Every submitted row was missing a ticker - refusing to store an empty index snapshot.',
				array( 'status' => 400 )
			);
		}

		$numeric_or_null = function ( $value ) {
			return isset( $value ) && null !== $value ? (float) $value : null;
		};

		$snapshot = array(
			'as_of'                => sanitize_text_field( $body['as_of'] ?? gmdate( 'c' ) ),
			'total_index_value'    => $numeric_or_null( $body['total_index_value'] ?? null ),
			'daily_change_dollar'  => $numeric_or_null( $body['daily_change_dollar'] ?? null ),
			'daily_change_percent' => $numeric_or_null( $body['daily_change_percent'] ?? null ),
			'ytd_change_percent'   => $numeric_or_null( $body['ytd_change_percent'] ?? null ),
			'constituent_count'    => count( $constituents ),
			'constituents'         => $constituents,
		);

		update_post_meta( $show_id, 'ng_index_snapshot', $snapshot );
		update_post_meta( $show_id, 'ng_index_last_refresh_date', current_time( 'Y-m-d' ) );
		update_post_meta(
			$show_id,
			'ng_index_last_refresh_status',
			array(
				'status'  => 'success',
				'at'      => gmdate( 'c' ),
				'message' => '',
			)
		);

		return rest_ensure_response(
			array(
				'stored'            => true,
				'constituent_count' => count( $constituents ),
			)
		);
	}
}
