<?php
/**
 * Per-show secret storage (Spec Section 3.3) plus the real YouTube OAuth
 * flow (Spec Section 6.3's "Connect YouTube channel" action). Only YouTube
 * OAuth tokens are genuinely per-show secrets in this system - everything
 * else (Anthropic, Captivate, GCP) is shared studio-wide.
 *
 * The authorization-code exchange and token refresh both happen here, in
 * WordPress, never in Python - Python has no public-facing endpoint at all
 * (it's a pure cron script), so it cannot be Google's OAuth redirect target,
 * and handing Python the refresh token would also require handing it the
 * OAuth client secret (Google's token endpoint needs both together), which
 * would duplicate that secret's source of truth. Python instead calls
 * youtube-access-token each tick and receives only a short-lived (~1hr)
 * access token - the refresh token and client secret never leave this file.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Secrets {

	const SECRET_KEY = 'youtube_oauth';

	// One static, studio-wide redirect URI - Google matches redirect_uri
	// exactly, so a per-show path (e.g. with a show id in it) would mean
	// registering a new one per show, which doesn't work. show_id travels
	// in the OAuth `state` parameter instead (see connect_youtube() in
	// class-admin-actions.php).
	public static function callback_url() {
		return rest_url( 'net-gain/v1/youtube-oauth-callback' );
	}

	public function register_routes() {
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

		// Public - this is Google's own browser-redirect target, reached by the
		// show owner's browser mid-flow, not by an authenticated API client.
		// Security rests entirely on the single-use `state` parameter (RFC 6749
		// §10.12), not on current_user_can() - whether a logged-in user's
		// capabilities are even reliably available to a REST callback reached via
		// a plain browser redirect (vs. an XHR carrying the REST nonce) has not
		// been verified, so state is treated as sufficient on its own, not as a
		// second layer on top of an unverified one.
		register_rest_route(
			'net-gain/v1',
			'/youtube-oauth-callback',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'oauth_callback' ),
				'permission_callback' => '__return_true',
			)
		);

		// The single most security-sensitive route in this project: a valid
		// request mints a live, bearer-capable access token. Gated to
		// edit_ng_shows (admin or the ng_service account only) - deliberately
		// stricter than the status route's can_act_for_show, since talent must
		// not be able to mint a channel-controlling token.
		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/youtube-access-token',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'mint_access_token' ),
				'permission_callback' => function () {
					return current_user_can( 'edit_ng_shows' );
				},
			)
		);
	}

	public function status( WP_REST_Request $request ) {
		$show_id   = (int) $request['id'];
		$connected = Net_Gain_Secrets::exists( 'show', $show_id, self::SECRET_KEY );

		return rest_ensure_response(
			array(
				'connected'     => $connected,
				'channel_id'    => $connected ? get_post_meta( $show_id, 'ng_youtube_channel_id', true ) : '',
				'channel_title' => $connected ? get_post_meta( $show_id, 'ng_youtube_channel_title', true ) : '',
			)
		);
	}

	public function oauth_callback( WP_REST_Request $request ) {
		$state = sanitize_text_field( (string) $request->get_param( 'state' ) );
		$code  = sanitize_text_field( (string) $request->get_param( 'code' ) );
		$error = sanitize_text_field( (string) $request->get_param( 'error' ) );

		$state_data = $state ? get_transient( 'ng_youtube_oauth_state_' . $state ) : false;
		if ( $state ) {
			delete_transient( 'ng_youtube_oauth_state_' . $state );
		}

		if ( ! $state_data || empty( $state_data['show_id'] ) ) {
			wp_die( 'This YouTube connection link has expired or was already used. Go back to the show setup screen and click Connect YouTube Channel again.' );
		}
		$show_id = (int) $state_data['show_id'];

		if ( $error || ! $code ) {
			return $this->redirect_to_edit_show( $show_id, 'youtube_connect_failed' );
		}

		$token_response = $this->request_google_token(
			array(
				'grant_type'   => 'authorization_code',
				'code'         => $code,
				'redirect_uri' => self::callback_url(),
			)
		);
		if ( is_wp_error( $token_response ) ) {
			return $this->redirect_to_edit_show( $show_id, 'youtube_connect_failed' );
		}

		$refresh_token = $token_response['refresh_token'] ?? '';
		$access_token  = $token_response['access_token'] ?? '';
		if ( ! $refresh_token || ! $access_token ) {
			// Classic symptom: Google only issues a refresh token on a user's FIRST
			// consent for this app+scope combination. connect_youtube() already
			// requests prompt=consent specifically to avoid this, but a user who
			// previously revoked and is re-consenting can still hit it.
			return $this->redirect_to_edit_show( $show_id, 'youtube_connect_failed' );
		}

		// Verify the grant actually works and capture channel identity before
		// trusting it - same "re-query and confirm before trusting" discipline
		// already applied to Captivate/website publishing (Spec Section 9).
		$channel = $this->fetch_own_channel( $access_token );
		if ( is_wp_error( $channel ) ) {
			return $this->redirect_to_edit_show( $show_id, 'youtube_connect_failed' );
		}

		$payload = array(
			'refresh_token' => $refresh_token,
			'scope'         => $token_response['scope'] ?? '',
			'obtained_at'   => current_time( 'mysql' ),
			'channel_id'    => $channel['id'],
			'channel_title' => $channel['title'],
		);
		Net_Gain_Secrets::set( 'show', $show_id, self::SECRET_KEY, wp_json_encode( $payload ) );

		update_post_meta( $show_id, 'ng_youtube_channel_id', $channel['id'] );
		update_post_meta( $show_id, 'ng_youtube_channel_title', $channel['title'] );
		update_post_meta( $show_id, 'ng_youtube_phone_verified', $channel['long_uploads_status'] );

		return $this->redirect_to_edit_show( $show_id, 'youtube_connected' );
	}

	public function mint_access_token( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$stored  = Net_Gain_Secrets::get( 'show', $show_id, self::SECRET_KEY );
		if ( is_wp_error( $stored ) ) {
			return $stored;
		}

		$payload       = $stored ? json_decode( $stored, true ) : null;
		$refresh_token = is_array( $payload ) ? ( $payload['refresh_token'] ?? '' ) : '';
		if ( ! $refresh_token ) {
			return new WP_Error(
				'ng_youtube_not_connected',
				'This show has no YouTube channel connected.',
				array( 'status' => 409 )
			);
		}

		$token_response = $this->request_google_token(
			array(
				'grant_type'    => 'refresh_token',
				'refresh_token' => $refresh_token,
			)
		);
		if ( is_wp_error( $token_response ) ) {
			// Deliberately a 5xx, not a 4xx - so the Python side's existing
			// retry-on-5xx wrapper applies to this the same as any other
			// transient WordPress-API failure.
			return new WP_Error(
				'ng_youtube_token_refresh_failed',
				$token_response->get_error_message(),
				array( 'status' => 502 )
			);
		}

		$access_token = $token_response['access_token'] ?? '';
		if ( ! $access_token ) {
			return new WP_Error(
				'ng_youtube_token_refresh_failed',
				'Google did not return an access token.',
				array( 'status' => 502 )
			);
		}

		return rest_ensure_response(
			array(
				'access_token' => $access_token,
				'expires_in'   => $token_response['expires_in'] ?? 3600,
				'channel_id'   => get_post_meta( $show_id, 'ng_youtube_channel_id', true ),
			)
		);
	}

	private function redirect_to_edit_show( $show_id, $notice ) {
		wp_safe_redirect(
			add_query_arg(
				array(
					'page'      => Net_Gain_Admin_Menu::EDIT_SLUG,
					'show_id'   => $show_id,
					'ng_notice' => $notice,
				),
				admin_url( 'admin.php' )
			)
		);
		exit;
	}

	/**
	 * Shared by both the authorization-code exchange and the refresh-token
	 * grant - the two differ only in which grant params they pass. Client
	 * id/secret come from wp-config.php constants (Section 3.3's studio-owned-
	 * secret pattern), never from Python's .env - Python never participates in
	 * this handshake.
	 */
	private function request_google_token( array $grant_params ) {
		if ( ! defined( 'NET_GAIN_YOUTUBE_CLIENT_ID' ) || ! defined( 'NET_GAIN_YOUTUBE_CLIENT_SECRET' )
			|| ! NET_GAIN_YOUTUBE_CLIENT_ID || ! NET_GAIN_YOUTUBE_CLIENT_SECRET ) {
			return new WP_Error( 'ng_youtube_not_configured', 'NET_GAIN_YOUTUBE_CLIENT_ID / NET_GAIN_YOUTUBE_CLIENT_SECRET are not defined in wp-config.php.' );
		}

		$body = array_merge(
			array(
				'client_id'     => NET_GAIN_YOUTUBE_CLIENT_ID,
				'client_secret' => NET_GAIN_YOUTUBE_CLIENT_SECRET,
			),
			$grant_params
		);

		// FLAG: token endpoint URL and parameter/response field names here are
		// this build's best understanding of Google's OAuth 2.0 token endpoint,
		// not verified against a live response - check against current Google
		// Identity Platform docs before the first real connection attempt.
		$response = wp_remote_post(
			'https://oauth2.googleapis.com/token',
			array(
				'body'    => $body,
				'timeout' => 30,
			)
		);
		if ( is_wp_error( $response ) ) {
			return $response;
		}

		$status_code = wp_remote_retrieve_response_code( $response );
		$parsed      = json_decode( wp_remote_retrieve_body( $response ), true );

		if ( 200 !== $status_code ) {
			$error_code = is_array( $parsed ) ? ( $parsed['error'] ?? '' ) : '';
			if ( 'invalid_grant' === $error_code ) {
				// Means either the channel owner revoked access, or (while this
				// app's OAuth consent screen remains in Google's "Testing"
				// publishing status, confirmed the case for this project at
				// build time) the refresh token hit Google's 7-day testing-mode
				// expiry. Either way the fix is reconnecting, not retrying.
				return new WP_Error(
					'ng_youtube_invalid_grant',
					'Google rejected this refresh token (invalid_grant) - the channel owner revoked access, or (while this app is in Google\'s "Testing" publishing status) the 7-day testing-mode refresh-token expiry was hit. Reconnect the channel.'
				);
			}
			return new WP_Error(
				'ng_youtube_token_request_failed',
				'Google token endpoint returned ' . $status_code . ': ' . wp_remote_retrieve_body( $response )
			);
		}

		if ( ! is_array( $parsed ) ) {
			return new WP_Error( 'ng_youtube_token_request_failed', 'Google token endpoint returned a non-JSON response: ' . wp_remote_retrieve_body( $response ) );
		}

		return $parsed;
	}

	/**
	 * Re-queries the channel directly with the fresh access token, both to
	 * verify the grant genuinely works before we trust it and to capture the
	 * channel's real identity (id/title) and phone-verification proxy.
	 *
	 * FLAG: status.longUploadsStatus is the best available proxy for phone
	 * verification found during planning (no YouTube API field documents this
	 * directly) - verify against a live response, not just this comment.
	 */
	private function fetch_own_channel( $access_token ) {
		$response = wp_remote_get(
			'https://www.googleapis.com/youtube/v3/channels?part=id,snippet,status&mine=true',
			array(
				'headers' => array( 'Authorization' => 'Bearer ' . $access_token ),
				'timeout' => 30,
			)
		);
		if ( is_wp_error( $response ) ) {
			return $response;
		}

		$status_code = wp_remote_retrieve_response_code( $response );
		$body        = json_decode( wp_remote_retrieve_body( $response ), true );

		if ( 200 !== $status_code || empty( $body['items'][0] ) ) {
			return new WP_Error( 'ng_youtube_channel_lookup_failed', 'Could not verify the YouTube channel: ' . wp_remote_retrieve_body( $response ) );
		}

		$item = $body['items'][0];
		return array(
			'id'                  => $item['id'] ?? '',
			'title'               => $item['snippet']['title'] ?? '',
			'long_uploads_status' => $item['status']['longUploadsStatus'] ?? 'unknown',
		);
	}
}
