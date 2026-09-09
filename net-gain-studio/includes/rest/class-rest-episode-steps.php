<?php
/**
 * Per-step status updates (prerequisite-validated, Spec Section 8.3), audio
 * intake (Section 8.1), and the talent-facing abort/publish-now controls for
 * the upload countdown (Section 8.1). Countdown elapse itself is detected
 * server-side by the Python tick loop, not here - the visible countdown
 * reflects that state, it isn't the source of truth for it.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Episode_Steps {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/steps/(?P<step_key>[a-z_]+)',
			array(
				'methods'             => 'PATCH',
				'callback'            => array( $this, 'update_step' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_episode( (int) $request['id'] );
				},
				'args'                => array(
					'status' => array( 'required' => true, 'type' => 'string' ),
					'note'   => array( 'required' => false, 'type' => 'string' ),
				),
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/audio',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'upload_audio' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_act_on_episode_finalization( (int) $request['id'] );
				},
				'args'                => array(
					'attachment_id' => array( 'required' => true, 'type' => 'integer' ),
				),
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/finalize-action',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'finalize_action' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_act_on_episode_finalization( (int) $request['id'] );
				},
				'args'                => array(
					'action' => array( 'required' => true, 'type' => 'string' ), // abort|publish_now
				),
			)
		);
	}

	public function update_step( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];

		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$step_status = is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status();

		$result = Net_Gain_Step_Status::apply_update(
			$step_status,
			$request['step_key'],
			$request->get_param( 'status' ),
			$request->get_param( 'note' ) ?: ''
		);
		if ( is_wp_error( $result ) ) {
			return $result;
		}

		update_post_meta( $episode_id, 'ng_step_status', $result );
		return rest_ensure_response( $result[ $request['step_key'] ] );
	}

	/**
	 * Handles both a first audio upload and a replacement upload after an
	 * abort identically - either way, a successful upload (re)starts a fresh
	 * countdown (Spec Section 8.1: "which starts a fresh countdown of its own").
	 */
	public function upload_audio( WP_REST_Request $request ) {
		$episode_id    = (int) $request['id'];
		$attachment_id = (int) $request->get_param( 'attachment_id' );

		if ( ! wp_attachment_is( 'audio', $attachment_id ) ) {
			return new WP_Error( 'ng_invalid_attachment', 'That attachment is not an audio file.', array( 'status' => 400 ) );
		}

		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$step_status = is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status();

		$result = Net_Gain_Step_Status::apply_update( $step_status, 'audio_received', 'done' );
		if ( is_wp_error( $result ) ) {
			return $result;
		}

		update_post_meta( $episode_id, 'ng_audio_attachment_id', $attachment_id );
		update_post_meta( $episode_id, 'ng_step_status', $result );

		// 90s is a code-tunable default (Section 11's confirmed Show fields don't
		// include a per-show override) rather than a new admin-screen field.
		$countdown_seconds = apply_filters( 'net_gain_finalization_countdown_seconds', 90, $episode_id );
		$finalization = array(
			'state' => 'counting_down',
			// GMT, not site-local (current_time('mysql')'s default) - this is an
			// internal value the Python tick loop does elapsed-time math against,
			// not something displayed to a person, so it must be unambiguous
			// regardless of the WP site's configured timezone (Spec Section 1:
			// "never assume a host's timezone").
			'countdown_started_at' => current_time( 'mysql', true ),
			'countdown_seconds'    => $countdown_seconds,
		);
		update_post_meta( $episode_id, 'ng_finalization', $finalization );

		return rest_ensure_response(
			array(
				'step_status'  => $result['audio_received'],
				'finalization' => $finalization,
			)
		);
	}

	/**
	 * Scoped deliberately to the audio-intake countdown only (state must be
	 * counting_down) - extending abort/publish-now to a later "queued,
	 * waiting on a real scheduled publish" state is a Phase 5+ concern once
	 * that actually exists to override.
	 */
	public function finalize_action( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$action     = $request->get_param( 'action' );

		if ( ! in_array( $action, array( 'abort', 'publish_now' ), true ) ) {
			return new WP_Error( 'ng_invalid_action', 'action must be "abort" or "publish_now".', array( 'status' => 400 ) );
		}

		$finalization  = get_post_meta( $episode_id, 'ng_finalization', true );
		$finalization  = is_array( $finalization ) ? $finalization : array();
		$current_state = $finalization['state'] ?? 'pending';

		if ( 'counting_down' !== $current_state ) {
			return new WP_Error(
				'ng_nothing_to_finalize',
				"Cannot {$action}: this episode is not currently in the finalization countdown (state: {$current_state}).",
				array( 'status' => 409 )
			);
		}

		$finalization['state']          = 'abort' === $action ? 'awaiting_replacement' : 'finalized';
		if ( 'publish_now' === $action ) {
			// GMT, matching countdown_started_at - Phase 5's scheduled-publish timing
			// computation needs an unambiguous "when did this actually finalize" moment.
			$finalization['finalized_at'] = current_time( 'mysql', true );
		}
		$finalization['last_action']    = $action;
		$finalization['last_action_at'] = current_time( 'mysql' );
		$finalization['last_action_by'] = get_current_user_id();

		update_post_meta( $episode_id, 'ng_finalization', $finalization );
		return rest_ensure_response( $finalization );
	}
}
