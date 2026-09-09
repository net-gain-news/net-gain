<?php
/**
 * TEMPORARY diagnostic route - added during live Phase 3-7 deployment
 * troubleshooting (2026-09-09) to see WordPress's actual authentication
 * state directly instead of guessing further. Deliberately open
 * (permission_callback => '__return_true') so it's reachable regardless of
 * whether auth is working - that's the whole point. Remove once the
 * Application Password issue is resolved; never leave this shipped.
 *
 * Reports presence-only booleans for server auth headers, never their
 * values, even though this is over HTTPS to a route only we're hitting -
 * no reason to echo a credential back even diagnostically.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Debug_Auth {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/debug-auth',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'report' ),
				'permission_callback' => '__return_true',
			)
		);
	}

	public function report( WP_REST_Request $request ) {
		$user = wp_get_current_user();

		return rest_ensure_response(
			array(
				'is_user_logged_in'        => is_user_logged_in(),
				'current_user_id'          => $user ? $user->ID : 0,
				'current_user_login'       => $user ? $user->user_login : '',
				'current_user_roles'       => $user ? $user->roles : array(),
				'can_edit_ng_shows'        => current_user_can( 'edit_ng_shows' ),
				'has_HTTP_AUTHORIZATION'   => isset( $_SERVER['HTTP_AUTHORIZATION'] ),
				'has_REDIRECT_HTTP_AUTHORIZATION' => isset( $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ),
				'php_auth_user_present'    => isset( $_SERVER['PHP_AUTH_USER'] ),
				'application_passwords_available' => function_exists( 'wp_is_application_passwords_available' ) ? wp_is_application_passwords_available() : 'function_missing',
			)
		);
	}
}
