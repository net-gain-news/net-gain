<?php
/**
 * PodcastEpisode JSON-LD (Spec Section 6.2) - hand-rolled via wp_head,
 * deliberately not relying on AIOSEO, which has no documented support for
 * this schema type (confirmed against its own docs before building this,
 * matching what the spec already assumed).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Schema_Output {

	public static function register() {
		add_action( 'wp_head', array( __CLASS__, 'output_schema' ) );
	}

	public static function output_schema() {
		if ( ! is_singular( 'podcast' ) ) {
			return;
		}

		$post_id   = get_the_ID();
		$audio_url = get_post_meta( $post_id, 'audio_file', true );

		$terms     = get_the_terms( $post_id, 'series' );
		$show_name = ( ! empty( $terms ) && ! is_wp_error( $terms ) ) ? $terms[0]->name : get_bloginfo( 'name' );

		$schema = array(
			'@context'      => 'https://schema.org',
			'@type'         => 'PodcastEpisode',
			'name'          => get_the_title( $post_id ),
			'url'           => get_permalink( $post_id ),
			'datePublished' => get_the_date( 'c', $post_id ),
			'partOfSeries'  => array(
				'@type' => 'PodcastSeries',
				'name'  => $show_name,
			),
		);

		if ( $audio_url ) {
			$schema['associatedMedia'] = array(
				'@type'      => 'MediaObject',
				'contentUrl' => $audio_url,
			);
		}

		$author_id = get_post_field( 'post_author', $post_id );
		if ( $author_id ) {
			$schema['author'] = array(
				'@type' => 'Person',
				'name'  => get_the_author_meta( 'display_name', $author_id ),
			);
		}

		// str_replace guards against generated title/description text containing a
		// literal "</script>" substring and breaking out of the tag early.
		$json = str_replace( '</script>', '<\/script>', wp_json_encode( $schema ) );
		echo '<script type="application/ld+json">' . $json . "</script>\n";
	}
}
