<?php
/**
 * Seeds a Show's guidelines page from its Vertical's template content, once,
 * at creation time (Spec Section 11: "seeds starting guidelines; fully
 * editable afterward"). Never called again after the first save - guidelines
 * become a normal WordPress page from that point on, edited inline from the
 * Show admin screen (2026-09-24) rather than via its own separate edit link.
 *
 * post_status is 'private', not 'publish' (2026-09-24, operator request):
 * this page is an internal working document - not meant to have a real,
 * publicly-reachable front-end URL just because it was never added to a nav
 * menu. 'private' still lets get_post_field()/wp_editor() read and write it
 * from the admin screen, and still lets the Python pipeline's Application-
 * Password-authenticated REST request read it (that user has read_private_pages
 * capability as an administrator) - only a logged-out visitor is blocked.
 * The _ng_is_guidelines_page meta flag drives the belt-and-suspenders
 * wp_robots noindex below, in case status ever reverts to public by mistake.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Guidelines {

	public static function register() {
		add_filter( 'wp_robots', array( __CLASS__, 'noindex_guidelines_pages' ) );
	}

	public static function seed_page_for_show( $show_id, $vertical_id ) {
		$show   = get_post( $show_id );
		$vertical_content = $vertical_id ? get_post_field( 'post_content', $vertical_id ) : '';

		// Not added to any nav menu - reached only via the Show admin screen's inline editor.
		$page_id = wp_insert_post(
			array(
				'post_type'    => 'page',
				'post_status'  => 'private',
				'post_title'   => $show ? $show->post_title . ' — Editorial Guidelines' : 'Editorial Guidelines',
				'post_content' => $vertical_content,
			)
		);

		if ( is_wp_error( $page_id ) || ! $page_id ) {
			return 0;
		}

		update_post_meta( $page_id, '_ng_is_guidelines_page', true );
		update_post_meta( $show_id, 'ng_guidelines_page_id', $page_id );
		return $page_id;
	}

	public static function noindex_guidelines_pages( $robots ) {
		$queried_id = get_queried_object_id();
		if ( $queried_id && get_post_meta( $queried_id, '_ng_is_guidelines_page', true ) ) {
			$robots['noindex']  = true;
			$robots['nofollow'] = true;
		}
		return $robots;
	}
}
