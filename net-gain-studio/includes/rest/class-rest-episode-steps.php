<?php
/**
 * Per-step status updates (prerequisite-validated, Spec Section 8.3) and the
 * talent-facing abort/publish-now controls for the upload countdown and
 * publish queue (Section 8.1/8.2). This route records state transitions and
 * enforces authorization; the actual side effects (stopping a timer,
 * triggering a real publish) are the tick loop's job in a later phase.
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
		$step_key   = $request['step_key'];
		$status     = $request->get_param( 'status' );

		if ( ! Net_Gain_Step_Status::is_valid_step( $step_key ) ) {
			return new WP_Error( 'ng_invalid_step', 'Unknown step: ' . $step_key, array( 'status' => 400 ) );
		}
		if ( ! Net_Gain_Step_Status::is_valid_status( $status ) ) {
			return new WP_Error( 'ng_invalid_status', 'Unknown status: ' . $status, array( 'status' => 400 ) );
		}

		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$step_status = is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status();

		$blocker = Net_Gain_Step_Status::unmet_prerequisite( $step_key, $step_status );
		if ( $blocker && 'pending' !== $status ) {
			return new WP_Error(
				'ng_prerequisite_not_met',
				"Cannot set {$step_key} to {$status}: prerequisite step \"{$blocker}\" is not done yet.",
				array( 'status' => 409 )
			);
		}

		$step_status[ $step_key ] = array(
			'status' => $status,
			'at'     => current_time( 'mysql' ),
			'note'   => $request->get_param( 'note' ) ?: '',
		);

		update_post_meta( $episode_id, 'ng_step_status', $step_status );
		return rest_ensure_response( $step_status[ $step_key ] );
	}

	public function finalize_action( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$action     = $request->get_param( 'action' );

		if ( ! in_array( $action, array( 'abort', 'publish_now' ), true ) ) {
			return new WP_Error( 'ng_invalid_action', 'action must be "abort" or "publish_now".', array( 'status' => 400 ) );
		}

		$finalization = get_post_meta( $episode_id, 'ng_finalization', true );
		$finalization = is_array( $finalization ) ? $finalization : array();

		$finalization['state'] = 'abort' === $action ? 'awaiting_replacement' : 'publish_now_requested';
		$finalization['last_action']    = $action;
		$finalization['last_action_at'] = current_time( 'mysql' );
		$finalization['last_action_by'] = get_current_user_id();

		update_post_meta( $episode_id, 'ng_finalization', $finalization );
		return rest_ensure_response( $finalization );
	}
}
