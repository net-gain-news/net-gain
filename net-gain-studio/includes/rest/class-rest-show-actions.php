<?php
/**
 * Manual-trigger queue (Spec Section 8.3). A pending action is just a
 * "look at this now" doorbell for the tick loop - it is never itself the
 * source of truth for whether a step already ran (that's ng_step_status on
 * the Episode). This is what makes manual and scheduled triggers genuinely
 * interchangeable rather than additive.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Show_Actions {

	const ALLOWED_ACTIONS = array( 'generate_script', 'generate_images', 'publish_captivate' );

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/actions',
			array(
				array(
					'methods'             => 'GET',
					'callback'            => array( $this, 'list_actions' ),
					'permission_callback' => function ( WP_REST_Request $request ) {
						return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
					},
				),
				array(
					'methods'             => 'POST',
					'callback'            => array( $this, 'enqueue_action' ),
					'permission_callback' => function ( WP_REST_Request $request ) {
						return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
					},
					'args'                => array(
						'action' => array( 'required' => true, 'type' => 'string' ),
						'episode_date' => array( 'required' => false, 'type' => 'string' ),
					),
				),
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/actions/(?P<action_id>[a-zA-Z0-9_-]+)',
			array(
				'methods'             => 'PATCH',
				'callback'            => array( $this, 'update_action' ),
				'permission_callback' => function () {
					return current_user_can( 'edit_ng_shows' ); // service account or admin only.
				},
				'args'                => array(
					'status' => array( 'required' => true, 'type' => 'string' ),
				),
			)
		);
	}

	public function list_actions( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		return rest_ensure_response( get_post_meta( $show_id, 'ng_pending_actions', true ) );
	}

	public function enqueue_action( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$action  = $request->get_param( 'action' );

		if ( ! in_array( $action, self::ALLOWED_ACTIONS, true ) ) {
			return new WP_Error( 'ng_invalid_action', 'Unknown action: ' . $action, array( 'status' => 400 ) );
		}

		$entry = array(
			'id'           => wp_generate_uuid4(),
			'action'       => $action,
			'episode_date' => $request->get_param( 'episode_date' ) ?: current_time( 'Y-m-d' ),
			'requested_at' => current_time( 'mysql' ),
			'requested_by' => get_current_user_id(),
			'status'       => 'pending',
		);

		$pending   = get_post_meta( $show_id, 'ng_pending_actions', true );
		$pending   = is_array( $pending ) ? $pending : array();
		$pending[] = $entry;
		update_post_meta( $show_id, 'ng_pending_actions', $pending );

		return rest_ensure_response( $entry );
	}

	public function update_action( WP_REST_Request $request ) {
		$show_id   = (int) $request['id'];
		$action_id = $request['action_id'];
		$status    = $request->get_param( 'status' );

		$pending = get_post_meta( $show_id, 'ng_pending_actions', true );
		$pending = is_array( $pending ) ? $pending : array();
		$found   = false;

		foreach ( $pending as &$entry ) {
			if ( $entry['id'] === $action_id ) {
				$entry['status'] = $status;
				$found = true;
				break;
			}
		}
		unset( $entry );

		if ( ! $found ) {
			return new WP_Error( 'ng_action_not_found', 'No such pending action.', array( 'status' => 404 ) );
		}

		update_post_meta( $show_id, 'ng_pending_actions', $pending );
		return rest_ensure_response( array( 'updated' => true ) );
	}
}
