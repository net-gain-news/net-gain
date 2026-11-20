<?php
/**
 * The visible internal links (2026-11-19): the "related newscasts" block at the bottom of each episode page, the topic
 * chips on episode and archive rows, and the topic strip on the show home. All of it is plain HTML with real anchors and
 * descriptive link text - nothing is injected by script - so a crawler following links finds every newscast and topic.
 *
 * The markup reuses the theme's own classes (ep-card, arch, mono, the colour variables) and its look comes from
 * assets/internal-links.css, so the block follows the active show colours. The theme calls the three functions at the
 * bottom of this file, guarded by function_exists(), so deactivating the plugin can never break a page.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Internal_Links {

	public static function register() {
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue' ) );
	}

	public static function enqueue() {
		if ( ! is_singular( 'podcast' ) && ! is_page() ) {
			return;
		}
		$css = NET_GAIN_PLUGIN_DIR . 'assets/internal-links.css';
		wp_enqueue_style( 'ng-internal-links', plugin_dir_url( NET_GAIN_PLUGIN_FILE ) . 'assets/internal-links.css', array(), NET_GAIN_VERSION . '.' . (int) @filemtime( $css ) );
	}

	/** One topic as a link when it has its own page, otherwise as plain text (a link to a thin page would only dilute). */
	private static function chip( $show, $tag, $topics ) {
		$name = esc_html( $tag['name'] );
		if ( isset( $topics[ $tag['slug'] ] ) && $topics[ $tag['slug'] ]['count'] >= Net_Gain_Entities::MIN_TOPIC_EPISODES ) {
			return '<a class="ng-topic" href="' . esc_url( Net_Gain_Entities::topic_url( $show, $tag['slug'] ) ) . '">' . $name . '</a>';
		}
		return '<span class="ng-topic ng-topic-plain">' . $name . '</span>';
	}

	/** Chips for one published newscast (at most $max, linked ones first). Empty string when it has no tags. */
	public static function chips_html( $podcast_id, $max = 4 ) {
		$index = Net_Gain_Entities::index();
		$podcast_id = (int) $podcast_id;
		if ( ! isset( $index[ $podcast_id ] ) || ! $index[ $podcast_id ]['entities'] ) {
			return '';
		}
		$show   = $index[ $podcast_id ]['show'];
		$topics = Net_Gain_Entities::build_topics( $index, $show );
		$tags   = $index[ $podcast_id ]['entities'];
		usort(
			$tags,
			static function ( $a, $b ) use ( $topics ) {
				$ca = isset( $topics[ $a['slug'] ] ) ? $topics[ $a['slug'] ]['count'] : 0;
				$cb = isset( $topics[ $b['slug'] ] ) ? $topics[ $b['slug'] ]['count'] : 0;
				return ( $cb >= Net_Gain_Entities::MIN_TOPIC_EPISODES ) <=> ( $ca >= Net_Gain_Entities::MIN_TOPIC_EPISODES ) ?: $cb <=> $ca;
			}
		);
		$html = '';
		foreach ( array_slice( $tags, 0, max( 1, (int) $max ) ) as $tag ) {
			$html .= self::chip( $show, $tag, $topics ) . ' ';
		}
		return '<span class="ng-topic-line">' . trim( $html ) . '</span>';
	}

	/** The block at the bottom of an episode page. Empty string when the newscast is not in the index yet. */
	public static function related_html( $podcast_id ) {
		$index = Net_Gain_Entities::index();
		$podcast_id = (int) $podcast_id;
		if ( ! isset( $index[ $podcast_id ] ) ) {
			return '';
		}
		$show    = $index[ $podcast_id ]['show'];
		$topics  = Net_Gain_Entities::build_topics( $index, $show );
		$related = Net_Gain_Entities::related( $podcast_id );
		if ( ! $related ) {
			return '';
		}
		$has_shared = false;
		foreach ( $related as $row ) {
			$has_shared = $has_shared || (bool) $row['shared'];
		}

		$html  = '<section class="ng-related" aria-labelledby="ng-related-h">';
		$html .= '<h2 id="ng-related-h" class="arch ng-related-h">' . esc_html( $has_shared ? 'Related newscasts' : 'More newscasts' ) . '</h2>';

		$html .= '<div class="ng-related-grid">';
		foreach ( $related as $row ) {
			$entry = $row['entry'];
			$thumb = function_exists( 'ng_episode_thumb_img' ) ? ng_episode_thumb_img( $entry['id'], true ) : '';
			$why   = $row['shared'] ? 'Also covers ' . Net_Gain_Entities::join_names( array_slice( $row['shared'], 0, 3 ) ) : '';
			$html .= '<a class="ep-card ng-related-card" href="' . esc_url( $entry['url'] ) . '">';
			if ( $thumb ) {
				$html .= '<span class="ng-related-img">' . $thumb . '</span>'; // phpcs:ignore WordPress.Security.EscapeOutput -- built and escaped in ng_episode_thumb_img()
			}
			$html .= '<span class="ng-related-body">';
			$html .= '<span class="mono ng-related-date">' . esc_html( mysql2date( 'M j, Y', $entry['date'] ) ) . '</span>';
			$html .= '<span class="arch ng-related-title">' . esc_html( $entry['title'] ) . '</span>';
			if ( '' !== $why ) {
				$html .= '<span class="mono ng-related-why">' . esc_html( $why ) . '</span>';
			}
			$html .= '</span></a>';
		}
		$html .= '</div>';

		$html .= '<p class="ng-related-more mono">';
		$html .= '<a href="' . esc_url( home_url( '/' . $show . '/episodes/' ) ) . '">All newscasts &rarr;</a>';
		if ( Net_Gain_Entities::page_topics( $show ) ) {
			$html .= ' <a href="' . esc_url( Net_Gain_Entities::topics_index_url( $show ) ) . '">Browse by topic &rarr;</a>';
		}
		$html .= '</p></section>';
		return $html;
	}

	/** A strip of the show's biggest topics (for the show home page): linked names with their newscast counts. */
	public static function topics_strip_html( $show_slug, $limit = 10 ) {
		$topics = array_slice( Net_Gain_Entities::page_topics( $show_slug ), 0, max( 1, (int) $limit ), true );
		if ( ! $topics ) {
			return '';
		}
		$html = '<div class="ng-topic-strip"><span class="mono ng-related-label">Browse by topic</span> ';
		foreach ( $topics as $topic ) {
			$html .= '<a class="ng-topic" href="' . esc_url( Net_Gain_Entities::topic_url( $show_slug, $topic['slug'] ) ) . '">' . esc_html( $topic['name'] ) . ' <span class="ng-topic-count">' . (int) $topic['count'] . '</span></a> ';
		}
		$html .= '<a class="mono ng-topic-all" href="' . esc_url( Net_Gain_Entities::topics_index_url( $show_slug ) ) . '">All topics &rarr;</a></div>';
		return $html;
	}
}

/** Theme-facing wrappers (the theme guards each call with function_exists()). */
function net_gain_related_newscasts_html( $podcast_id ) {
	return Net_Gain_Internal_Links::related_html( $podcast_id );
}

function net_gain_topic_chips_html( $podcast_id, $max = 4 ) {
	return Net_Gain_Internal_Links::chips_html( $podcast_id, $max );
}

function net_gain_topics_strip_html( $show_slug, $limit = 10 ) {
	return Net_Gain_Internal_Links::topics_strip_html( $show_slug, $limit );
}
