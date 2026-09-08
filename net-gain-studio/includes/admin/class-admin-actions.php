<?php
/**
 * admin_post handlers for the Show setup screen. Kept separate from the
 * Captivate connect action (Section 6.1's own "explicit connection action")
 * so the two forms on the edit screen post independently.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Admin_Actions {

	public static function register() {
		add_action( 'admin_post_ng_save_show', array( __CLASS__, 'save_show' ) );
		add_action( 'admin_post_ng_connect_captivate', array( __CLASS__, 'connect_captivate' ) );
	}

	public static function save_show() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to do this.' );
		}
		check_admin_referer( 'ng_save_show', 'ng_save_show_nonce' );

		$show_id = isset( $_POST['show_id'] ) ? (int) $_POST['show_id'] : 0;
		$is_new  = 0 === $show_id;

		$postarr = array(
			'post_type'   => Net_Gain_CPT_Show::POST_TYPE,
			'post_status' => 'publish',
			'post_title'  => sanitize_text_field( wp_unslash( $_POST['ng_title'] ?? '' ) ),
			'post_name'   => sanitize_title( wp_unslash( $_POST['ng_slug'] ?? '' ) ),
		);

		if ( $is_new ) {
			$result  = wp_insert_post( $postarr, true );
			$show_id = is_wp_error( $result ) ? 0 : $result;
		} else {
			$postarr['ID'] = $show_id;
			$result        = wp_update_post( $postarr, true );
		}

		if ( is_wp_error( $result ) || ! $show_id ) {
			wp_die( 'Could not save show: ' . ( is_wp_error( $result ) ? esc_html( $result->get_error_message() ) : 'unknown error' ) );
		}

		self::save_meta( $show_id, $is_new );

		$primary_talent_id = isset( $_POST['ng_primary_talent'] ) ? (int) $_POST['ng_primary_talent'] : 0;
		if ( $primary_talent_id ) {
			Net_Gain_Talent_Assignments::set_primary( $show_id, $primary_talent_id );
		}

		if ( $is_new ) {
			$vertical_id = (int) get_post_meta( $show_id, 'ng_vertical_id', true );
			Net_Gain_Guidelines::seed_page_for_show( $show_id, $vertical_id );
		}

		wp_safe_redirect(
			add_query_arg(
				array(
					'page'      => Net_Gain_Admin_Menu::EDIT_SLUG,
					'show_id'   => $show_id,
					'ng_notice' => 'saved',
				),
				admin_url( 'admin.php' )
			)
		);
		exit;
	}

	private static function save_meta( $show_id, $is_new ) {
		// Vertical is set once at creation and never overwritten afterward (Section 4.1's
		// prospective-only-changes principle - the field is disabled in the UI on edit,
		// but we also refuse it server-side rather than trusting a hidden input alone).
		if ( $is_new ) {
			update_post_meta( $show_id, 'ng_vertical_id', (int) ( $_POST['ng_vertical_id'] ?? 0 ) );
		}

		update_post_meta( $show_id, 'ng_custom_domain', sanitize_text_field( wp_unslash( $_POST['ng_custom_domain'] ?? '' ) ) );

		$recording_days = isset( $_POST['ng_recording_days'] ) ? array_map( 'sanitize_key', wp_unslash( (array) $_POST['ng_recording_days'] ) ) : array();
		update_post_meta( $show_id, 'ng_recording_days', $recording_days );

		update_post_meta( $show_id, 'ng_target_time', sanitize_text_field( wp_unslash( $_POST['ng_target_time'] ?? '' ) ) );
		update_post_meta( $show_id, 'ng_recording_timezone', sanitize_text_field( wp_unslash( $_POST['ng_recording_timezone'] ?? '' ) ) );
		update_post_meta( $show_id, 'ng_lookback_days', max( 1, (int) ( $_POST['ng_lookback_days'] ?? 30 ) ) );

		$publish_mode = ( 'scheduled' === ( $_POST['ng_publish_mode'] ?? '' ) ) ? 'scheduled' : 'immediate';
		update_post_meta( $show_id, 'ng_publish_mode', $publish_mode );
		update_post_meta( $show_id, 'ng_publish_time', sanitize_text_field( wp_unslash( $_POST['ng_publish_time'] ?? '' ) ) );
		update_post_meta( $show_id, 'ng_publish_timezone', sanitize_text_field( wp_unslash( $_POST['ng_publish_timezone'] ?? '' ) ) );

		foreach ( array( 'ng_frame_square_id', 'ng_frame_16x9_id', 'ng_frame_1200x630_id' ) as $frame_key ) {
			update_post_meta( $show_id, $frame_key, (int) ( $_POST[ $frame_key ] ?? 0 ) );
		}

		$status = sanitize_key( $_POST['ng_status'] ?? 'active' );
		if ( ! in_array( $status, array( 'active', 'paused', 'concluded' ), true ) ) {
			$status = 'active';
		}
		update_post_meta( $show_id, 'ng_status', $status );
	}

	public static function connect_captivate() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to do this.' );
		}
		check_admin_referer( 'ng_connect_captivate', 'ng_connect_captivate_nonce' );

		$show_id = isset( $_POST['show_id'] ) ? (int) $_POST['show_id'] : 0;
		if ( ! $show_id || Net_Gain_CPT_Show::POST_TYPE !== get_post_type( $show_id ) ) {
			wp_die( 'Show not found.' );
		}

		update_post_meta( $show_id, 'ng_captivate_show_id', sanitize_text_field( wp_unslash( $_POST['ng_captivate_show_id'] ?? '' ) ) );

		wp_safe_redirect(
			add_query_arg(
				array(
					'page'      => Net_Gain_Admin_Menu::EDIT_SLUG,
					'show_id'   => $show_id,
					'ng_notice' => 'captivate_connected',
				),
				admin_url( 'admin.php' )
			)
		);
		exit;
	}
}
