<?php
/**
 * Per-show secret storage - currently just YouTube OAuth tokens (Spec
 * Section 3.3). Admin-only; the status route returns a boolean only and
 * never the stored value. The real OAuth authorization-code redirect/refresh
 * flow (Section 6.3's "Connect YouTube channel" action) is deferred to the
 * YouTube build phase - this just proves the storage primitive works.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Secrets {

	const SECRET_KEY = 'youtube_oauth';

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/secrets/youtube-oauth',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'store' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
				},
				'args'                => array(
					'payload' => array( 'required' => true, 'type' => 'object' ),
				),
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/secrets/youtube-oauth/status',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'status' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_act_for_show( (int) $request['id'] );
				},
			)
		);
	}

	// TODO(youtube-phase): replace this stub with the real OAuth redirect/refresh flow.
	public function store( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$payload = wp_json_encode( $request->get_param( 'payload' ) );

		$result = Net_Gain_Secrets::set( 'show', $show_id, self::SECRET_KEY, $payload );
		if ( is_wp_error( $result ) ) {
			return $result;
		}

		return rest_ensure_response( array( 'stored' => true ) );
	}

	public function status( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		return rest_ensure_response( array(
			'connected' => Net_Gain_Secrets::exists( 'show', $show_id, self::SECRET_KEY ),
		) );
	}
}
