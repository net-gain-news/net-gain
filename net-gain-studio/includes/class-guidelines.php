<?php
/**
 * Seeds a Show's guidelines page from its Vertical's template content, once,
 * at creation time (Spec Section 11: "seeds starting guidelines; fully
 * editable afterward"). Never called again after the first save - guidelines
 * become a normal WordPress page from that point on, edited directly.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Guidelines {

	public static function seed_page_for_show( $show_id, $vertical_id ) {
		$show   = get_post( $show_id );
		$vertical_content = $vertical_id ? get_post_field( 'post_content', $vertical_id ) : '';

		// Not added to any nav menu - reached only via the Show admin screen's "Edit Guidelines" link.
		$page_id = wp_insert_post(
			array(
				'post_type'    => 'page',
				'post_status'  => 'publish',
				'post_title'   => $show ? $show->post_title . ' — Editorial Guidelines' : 'Editorial Guidelines',
				'post_content' => $vertical_content,
			)
		);

		if ( is_wp_error( $page_id ) || ! $page_id ) {
			return 0;
		}

		update_post_meta( $show_id, 'ng_guidelines_page_id', $page_id );
		return $page_id;
	}
}
