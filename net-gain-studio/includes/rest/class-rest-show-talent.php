<?php
/**
 * Talent assignment routes - thin REST wrapper around
 * Net_Gain_Talent_Assignments (Spec Section 4's many-to-many + substitute
 * date ranges).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Show_Talent {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/talent',
			array(
				array(
					'methods'             => 'GET',
					'callback'            => array( $this, 'list_talent' ),
					'permission_callback' => function ( WP_REST_Request $request ) {
						return Net_Gain_REST_Permissions::can_act_for_show( (int) $request['id'] );
					},
				),
				array(
					'methods'             => 'POST',
					'callback'            => array( $this, 'add_talent' ),
					'permission_callback' => function ( WP_REST_Request $request ) {
						return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
					},
					'args'                => array(
						'role'       => array( 'required' => true, 'type' => 'string' ), // primary|substitute
						'user_id'    => array( 'required' => true, 'type' => 'integer' ),
						'start_date' => array( 'required' => false, 'type' => 'string' ),
						'end_date'   => array( 'required' => false, 'type' => 'string' ),
					),
				),
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/talent/(?P<assignment_id>\d+)',
			array(
				'methods'             => 'DELETE',
				'callback'            => array( $this, 'remove_talent' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
				},
			)
		);

		register_rest_route(
			'net-gain/v1',
			'/talent/(?P<user_id>\d+)/shows',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'shows_for_talent' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::is_self_or_admin( (int) $request['user_id'] );
				},
			)
		);
	}

	public function list_talent( WP_REST_Request $request ) {
		return rest_ensure_response( Net_Gain_Talent_Assignments::list_for_show( (int) $request['id'] ) );
	}

	public function add_talent( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$role    = $request->get_param( 'role' );
		$user_id = (int) $request->get_param( 'user_id' );

		if ( 'primary' === $role ) {
			$id = Net_Gain_Talent_Assignments::set_primary( $show_id, $user_id );
		} elseif ( 'substitute' === $role ) {
			$start = $request->get_param( 'start_date' );
			$end   = $request->get_param( 'end_date' );
			if ( ! $start || ! $end ) {
				return new WP_Error( 'ng_missing_dates', 'Substitute assignments require start_date and end_date.', array( 'status' => 400 ) );
			}
			$id = Net_Gain_Talent_Assignments::add_substitute( $show_id, $user_id, $start, $end );
		} else {
			return new WP_Error( 'ng_invalid_role', 'role must be "primary" or "substitute".', array( 'status' => 400 ) );
		}

		return rest_ensure_response( Net_Gain_Talent_Assignments::get( $id ) );
	}

	public function remove_talent( WP_REST_Request $request ) {
		$removed = Net_Gain_Talent_Assignments::remove( (int) $request['assignment_id'] );
		return rest_ensure_response( array( 'removed' => $removed ) );
	}

	public function shows_for_talent( WP_REST_Request $request ) {
		return rest_ensure_response( Net_Gain_Talent_Assignments::list_for_user( (int) $request['user_id'] ) );
	}
}
