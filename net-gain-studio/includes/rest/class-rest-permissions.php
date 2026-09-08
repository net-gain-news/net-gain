<?php
/**
 * Shared permission_callback helpers for the net-gain/v1 routes. Admin vs.
 * service-account access rides on the capabilities granted in
 * Net_Gain_Roles; talent's access to their own show/episode is a relationship
 * check against wp_ng_talent_assignments, not a WP capability - Section 12's
 * "talent sees only their own show(s)" is inherently relationship-based.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Permissions {

	public static function can_manage_shows() {
		return current_user_can( 'edit_ng_shows' );
	}

	public static function can_manage_show( $show_id ) {
		return current_user_can( 'edit_post', $show_id );
	}

	public static function can_manage_episode( $episode_id ) {
		return current_user_can( 'edit_post', $episode_id );
	}

	/** Admin, or the talent currently assigned (primary or covering today) to this show. */
	public static function can_act_for_show( $show_id ) {
		if ( self::can_manage_show( $show_id ) ) {
			return true;
		}
		return Net_Gain_Talent_Assignments::user_is_assigned_to_show( get_current_user_id(), $show_id );
	}

	/** Admin, or the specific talent who recorded this episode (or is currently covering its show). */
	public static function can_act_on_episode_finalization( $episode_id ) {
		if ( self::can_manage_episode( $episode_id ) ) {
			return true;
		}
		$show_id = wp_get_post_parent_id( $episode_id );
		return $show_id && Net_Gain_Talent_Assignments::user_is_assigned_to_show( get_current_user_id(), $show_id );
	}

	public static function is_self_or_admin( $user_id ) {
		return current_user_can( 'edit_ng_shows' ) || get_current_user_id() === (int) $user_id;
	}
}
