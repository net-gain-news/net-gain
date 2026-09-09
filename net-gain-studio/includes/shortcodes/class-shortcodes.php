<?php
/**
 * [net_gain_shows_hub] - Spec Section 6.2's cross-show "all our shows" page;
 * placed automatically on the auto-created /shows/ page, but provided as a
 * shortcode rather than hardcoded so an admin can move or customize it.
 * [net_gain_show_episodes] - a single show's episode list, placed on that
 * show's own auto-created hub page at /shows/{show-slug}/.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Shortcodes {

	public static function register() {
		add_shortcode( 'net_gain_shows_hub', array( __CLASS__, 'render_shows_hub' ) );
		add_shortcode( 'net_gain_show_episodes', array( __CLASS__, 'render_show_episodes' ) );
	}

	public static function render_shows_hub( $atts ) {
		$shows = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Show::POST_TYPE,
				'posts_per_page' => -1,
				'meta_query'     => array(
					array( 'key' => 'ng_status', 'value' => array( 'active', 'concluded' ), 'compare' => 'IN' ),
				),
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);

		if ( empty( $shows ) ) {
			return '';
		}

		$html = '<ul class="ng-shows-hub">';
		foreach ( $shows as $show ) {
			$url   = home_url( '/shows/' . $show->post_name . '/' );
			$html .= '<li><a href="' . esc_url( $url ) . '">' . esc_html( $show->post_title ) . '</a></li>';
		}
		$html .= '</ul>';
		return $html;
	}

	public static function render_show_episodes( $atts ) {
		$atts    = shortcode_atts( array( 'show_id' => 0 ), $atts );
		$show_id = (int) $atts['show_id'];
		$show    = $show_id ? get_post( $show_id ) : null;
		$term    = $show ? get_term_by( 'slug', $show->post_name, 'series' ) : null;

		if ( ! $term ) {
			return '<p>No episodes published yet.</p>';
		}

		$episodes = get_posts(
			array(
				'post_type'      => 'podcast',
				'posts_per_page' => -1,
				'tax_query'      => array(
					array( 'taxonomy' => 'series', 'field' => 'term_id', 'terms' => $term->term_id ),
				),
				'orderby'        => 'date',
				'order'          => 'DESC',
			)
		);

		if ( empty( $episodes ) ) {
			return '<p>No episodes published yet.</p>';
		}

		$html = '<ul class="ng-show-episodes">';
		foreach ( $episodes as $episode ) {
			$html .= '<li><a href="' . esc_url( get_permalink( $episode ) ) . '">' . esc_html( $episode->post_title ) . '</a></li>';
		}
		$html .= '</ul>';
		return $html;
	}
}
