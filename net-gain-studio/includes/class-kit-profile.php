<?php
/**
 * The welcome page's optional "help us know our audience" answers (role, organisation, job title) become custom fields on
 * the subscriber in Kit.
 *
 * Kit's own sign-up script sends the subscriber on to the welcome page and fires a page event with the address just before
 * it does (assets/signup-handoff.js keeps it for that tab). The welcome page then posts the answers to the route below,
 * which finds the subscriber in Kit by that address and writes the answers to them through Kit's v4 API. The API key is
 * the NET_GAIN_KIT_API_KEY constant in wp-config.php, or a stored secret (scope "site", key "kit_api_key"); until one is
 * present is_ready() is false and the welcome page does not show the form at all.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Kit_Profile {

	const API         = 'https://api.kit.com/v4';
	const FIELDS      = array(
		'role'         => 'Role',
		'organization' => 'Organization',
		'job_title'    => 'Job title',
	);
	const MAX_LENGTH  = 120;
	const READY_OPT   = 'ng_kit_profile_fields_ready';

	public static function register() {
		add_action( 'rest_api_init', array( __CLASS__, 'register_routes' ) );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue_handoff' ) );
	}

	public static function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/profile',
			array(
				'methods'             => 'POST',
				'callback'            => array( __CLASS__, 'handle' ),
				'permission_callback' => '__return_true',
			)
		);
	}

	public static function enqueue_handoff() {
		$file = NET_GAIN_PLUGIN_DIR . 'assets/signup-handoff.js';
		wp_enqueue_script( 'ng-signup-handoff', plugin_dir_url( NET_GAIN_PLUGIN_FILE ) . 'assets/signup-handoff.js', array(), NET_GAIN_VERSION . '.' . (int) @filemtime( $file ), true );
	}

	/* ----------------------------------------------------------------- pure parts */

	/** Kit derives a custom field's key from its label: lower case, anything else becomes an underscore. */
	public static function field_key( $label ) {
		return trim( preg_replace( '/[^a-z0-9]+/', '_', strtolower( (string) $label ) ), '_' );
	}

	/**
	 * Pure: what to send, or null when the request is not usable. Only the known answers are kept, each trimmed, stripped of
	 * tags and cut to a sane length; empty answers are dropped, and at least one must remain.
	 */
	public static function clean( array $input ) {
		$email = isset( $input['email'] ) && is_string( $input['email'] ) ? strtolower( trim( $input['email'] ) ) : '';
		if ( '' === $email || strlen( $email ) > 254 || ! preg_match( '/^[^@\s]+@[^@\s]+\.[^@\s]+$/', $email ) ) {
			return null;
		}
		$fields = array();
		foreach ( array_keys( self::FIELDS ) as $key ) {
			if ( ! isset( $input[ $key ] ) || ! is_string( $input[ $key ] ) ) {
				continue;
			}
			$value = trim( preg_replace( '/\s+/u', ' ', strip_tags( $input[ $key ] ) ) );
			if ( '' === $value ) {
				continue;
			}
			$fields[ $key ] = function_exists( 'mb_substr' ) ? mb_substr( $value, 0, self::MAX_LENGTH ) : substr( $value, 0, self::MAX_LENGTH );
		}
		return $fields ? array( 'email' => $email, 'fields' => $fields ) : null;
	}

	/* ----------------------------------------------------------------- Kit */

	public static function api_key() {
		if ( defined( 'NET_GAIN_KIT_API_KEY' ) && '' !== NET_GAIN_KIT_API_KEY ) {
			return (string) NET_GAIN_KIT_API_KEY;
		}
		if ( class_exists( 'Net_Gain_Secrets' ) ) {
			$stored = Net_Gain_Secrets::get( 'site', 0, 'kit_api_key' );
			if ( is_string( $stored ) && '' !== $stored ) {
				return $stored;
			}
		}
		return '';
	}

	public static function is_ready() {
		return '' !== self::api_key();
	}

	private static function call( $method, $path, $body = null ) {
		$args = array(
			'method'  => $method,
			'timeout' => 10,
			'headers' => array(
				'X-Kit-Api-Key' => self::api_key(),
				'Accept'        => 'application/json',
				'Content-Type'  => 'application/json',
			),
		);
		if ( null !== $body ) {
			$args['body'] = wp_json_encode( $body );
		}
		$response = wp_remote_request( self::API . $path, $args );
		if ( is_wp_error( $response ) ) {
			return array( 0, null );
		}
		return array( (int) wp_remote_retrieve_response_code( $response ), json_decode( wp_remote_retrieve_body( $response ), true ) );
	}

	/** Creates the three custom fields in Kit if they are not there yet (Kit answers 200 for one that exists, 201 for a new one). */
	public static function ensure_fields() {
		if ( get_option( self::READY_OPT ) === md5( wp_json_encode( self::FIELDS ) ) ) {
			return true;
		}
		foreach ( self::FIELDS as $label ) {
			list( $code ) = self::call( 'POST', '/custom_fields', array( 'label' => $label ) );
			if ( 200 !== $code && 201 !== $code ) {
				return false;
			}
		}
		update_option( self::READY_OPT, md5( wp_json_encode( self::FIELDS ) ), false );
		return true;
	}

	/** Writes the answers to the active subscriber with this address. True only when Kit confirmed the update. */
	public static function save_to_kit( $email, array $fields ) {
		if ( ! self::ensure_fields() ) {
			return false;
		}
		list( $code, $data ) = self::call( 'GET', '/subscribers?email_address=' . rawurlencode( $email ) );
		if ( 200 !== $code || empty( $data['subscribers'][0]['id'] ) || 'active' !== ( isset( $data['subscribers'][0]['state'] ) ? $data['subscribers'][0]['state'] : '' ) ) {
			return false;
		}
		$id = (int) $data['subscribers'][0]['id'];
		list( $code ) = self::call( 'PUT', '/subscribers/' . $id, array( 'email_address' => $email, 'fields' => $fields ) );
		return 200 === $code || 202 === $code;
	}

	private static function throttled( $email ) {
		$ip   = isset( $_SERVER['REMOTE_ADDR'] ) ? (string) $_SERVER['REMOTE_ADDR'] : '';
		$keys = array( 'ng_kp_e_' . md5( $email ) => 6, 'ng_kp_i_' . md5( $ip ) => 20 );
		foreach ( $keys as $key => $limit ) {
			$count = (int) get_transient( $key );
			if ( $count >= $limit ) {
				return true;
			}
			set_transient( $key, $count + 1, HOUR_IN_SECONDS );
		}
		return false;
	}

	public static function handle( WP_REST_Request $request ) {
		$generic_fail = new WP_REST_Response( array( 'ok' => false ), 400 );
		if ( ! self::is_ready() ) {
			return $generic_fail;
		}
		$params = $request->get_json_params();
		$clean  = self::clean( is_array( $params ) ? $params : array() );
		if ( ! $clean || self::throttled( $clean['email'] ) ) {
			return $generic_fail;
		}
		if ( ! self::save_to_kit( $clean['email'], $clean['fields'] ) ) {
			return $generic_fail;
		}
		return new WP_REST_Response( array( 'ok' => true ), 200 );
	}
}
