<?php
/**
 * Audio replacement routes (Spec Section 8.4). The first two are for people:
 * an administrator, or the show's designated host (the same relationship check
 * audio upload and abort/publish-now already use). The PATCH is for the Python
 * tick loop reporting each destination's progress.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Audio_Replacement {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/replace-audio',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'replace_audio' ),
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
			'/episodes/(?P<id>\d+)/replace-audio/retry',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'retry' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_act_on_episode_finalization( (int) $request['id'] );
				},
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/audio-replacement',
			array(
				'methods'             => 'PATCH',
				'callback'            => array( $this, 'update_destination' ),
				'permission_callback' => function () {
					return current_user_can( 'edit_ng_shows' ); // service account or admin only.
				},
				'args'                => array(
					'destination' => array( 'required' => true, 'type' => 'string' ),
					'status'      => array( 'required' => true, 'type' => 'string' ),
					'note'        => array( 'required' => false, 'type' => 'string' ),
					'data'        => array( 'required' => false, 'type' => 'object' ),
				),
			)
		);
	}

	private function episode_or_error( $episode_id ) {
		$episode = get_post( $episode_id );
		if ( ! $episode || Net_Gain_CPT_Episode::POST_TYPE !== $episode->post_type ) {
			return new WP_Error( 'ng_episode_not_found', 'Episode not found.', array( 'status' => 404 ) );
		}
		return $episode;
	}

	public function replace_audio( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$episode    = $this->episode_or_error( $episode_id );
		if ( is_wp_error( $episode ) ) {
			return $episode;
		}
		$result = Net_Gain_Audio_Replacement::request( $episode_id, (int) $request->get_param( 'attachment_id' ), get_current_user_id() );
		return is_wp_error( $result ) ? $result : rest_ensure_response( $result );
	}

	public function retry( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$episode    = $this->episode_or_error( $episode_id );
		if ( is_wp_error( $episode ) ) {
			return $episode;
		}
		$result = Net_Gain_Audio_Replacement::retry( $episode_id );
		return is_wp_error( $result ) ? $result : rest_ensure_response( $result );
	}

	public function update_destination( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$episode    = $this->episode_or_error( $episode_id );
		if ( is_wp_error( $episode ) ) {
			return $episode;
		}
		$data = $request->get_param( 'data' );
		$result = Net_Gain_Audio_Replacement::update_destination(
			$episode_id,
			$request->get_param( 'destination' ),
			$request->get_param( 'status' ),
			(string) $request->get_param( 'note' ),
			is_array( $data ) ? $data : array()
		);
		return is_wp_error( $result ) ? $result : rest_ensure_response( $result );
	}
}
