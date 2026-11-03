<?php
/**
 * Per-step status updates (prerequisite-validated, Spec Section 8.3) and audio
 * intake (Section 8.1). An upload is the publish decision: it finalizes the
 * episode on the spot and the background job takes it from there.
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
	 * The first audio upload is the publish decision: the episode is finalized at once, with no waiting period, and the
	 * background job publishes it on its next pass (immediately, or at the show's scheduled time). Fixing a wrong file
	 * afterwards is the "Replace audio" control, which works on a finalized episode.
	 */
	public function upload_audio( WP_REST_Request $request ) {
		$episode_id    = (int) $request['id'];
		$attachment_id = (int) $request->get_param( 'attachment_id' );

		if ( ! wp_attachment_is( 'audio', $attachment_id ) ) {
			return new WP_Error( 'ng_invalid_attachment', 'That attachment is not an audio file.', array( 'status' => 400 ) );
		}

		$existing = get_post_meta( $episode_id, 'ng_finalization', true );
		if ( is_array( $existing ) && 'finalized' === ( $existing['state'] ?? '' ) ) {
			return new WP_Error(
				'ng_already_finalized',
				'Audio has already been uploaded for this episode. Use "Replace audio" to swap the file.',
				array( 'status' => 409 )
			);
		}

		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$step_status = is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status();

		$result = Net_Gain_Step_Status::apply_update( $step_status, 'audio_received', 'done' );
		if ( is_wp_error( $result ) ) {
			return $result;
		}

		update_post_meta( $episode_id, 'ng_audio_attachment_id', $attachment_id );
		update_post_meta( $episode_id, 'ng_step_status', $result );

		$finalization = array(
			'state'        => 'finalized',
			// GMT, not site-local (current_time('mysql')'s default) - the Python job does time math against this (a
			// scheduled show's next publish moment), so it must be unambiguous regardless of the WP site's timezone
			// (Spec Section 1: "never assume a host's timezone").
			'finalized_at' => current_time( 'mysql', true ),
		);
		update_post_meta( $episode_id, 'ng_finalization', $finalization );

		return rest_ensure_response(
			array(
				'step_status'  => $result['audio_received'],
				'finalization' => $finalization,
			)
		);
	}
}
