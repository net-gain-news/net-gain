<?php
/**
 * Topics and entities (internal linking, 2026-11-19).
 *
 * The pipeline tags every episode with the companies, organizations, places and recurring topics it covers
 * (pipeline/entities.py) and stores them on the internal episode record as ng_entities: a list of
 * {name, slug, kind, note}. This class turns those tags into the three things the website needs:
 *
 *   - an index of every published newscast with its tags (cached),
 *   - topics: every tag with the newscasts that carry it, which become the /{show}/topics/{slug}/ pages,
 *   - related newscasts for one episode, chosen by the tags two newscasts share.
 *
 * Everything here is read-only and pure given the index, so the ranking is unit-tested without WordPress
 * (tests/entities-test.php).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Entities {

	const META_KEY = 'ng_entities';
	const CACHE    = 'ng_entity_index_v1';

	/** A topic gets its own indexable page only once it has this many newscasts and so is more than a thin list. */
	const MIN_TOPIC_EPISODES = 3;

	/** How many related newscasts an episode page shows. */
	const RELATED_LIMIT = 4;

	/** Singular label, plural label, and how much a shared tag of this kind says about two newscasts being alike. */
	public static function kinds() {
		return array(
			'company'      => array( 'Company', 'Companies', 3.0 ),
			'organization' => array( 'Organization', 'Organizations', 2.5 ),
			'place'        => array( 'Place', 'Places', 2.0 ),
			'topic'        => array( 'Topic', 'Topics', 1.5 ),
		);
	}

	public static function register() {
		add_action( 'updated_post_meta', array( __CLASS__, 'meta_changed' ), 10, 3 );
		add_action( 'added_post_meta', array( __CLASS__, 'meta_changed' ), 10, 3 );
		add_action( 'save_post_podcast', array( __CLASS__, 'flush' ) );
		add_action( 'deleted_post', array( __CLASS__, 'flush' ) );
		add_action( 'transition_post_status', array( __CLASS__, 'status_changed' ), 10, 3 );
	}

	public static function meta_changed( $meta_id, $post_id, $meta_key ) {
		if ( in_array( $meta_key, array( self::META_KEY, 'ng_website_post_id' ), true ) ) {
			self::flush();
		}
	}

	public static function status_changed( $new, $old, $post ) {
		if ( $post && 'podcast' === $post->post_type && $new !== $old ) {
			self::flush();
		}
	}

	public static function flush() {
		delete_transient( self::CACHE );
	}

	/* ------------------------------------------------------------------ pure helpers */

	/** Pure: a stored tag list reduced to well-formed tags (known kind, non-empty name and slug). */
	public static function clean_tags( $raw ) {
		$kinds = self::kinds();
		$out   = array();
		if ( ! is_array( $raw ) ) {
			return $out;
		}
		foreach ( $raw as $tag ) {
			if ( ! is_array( $tag ) ) {
				continue;
			}
			$name = isset( $tag['name'] ) ? trim( (string) $tag['name'] ) : '';
			$slug = isset( $tag['slug'] ) ? trim( (string) $tag['slug'] ) : '';
			$kind = isset( $tag['kind'] ) ? (string) $tag['kind'] : '';
			if ( '' === $name || ! preg_match( '/^[a-z0-9]+(?:-[a-z0-9]+)*$/', $slug ) || ! isset( $kinds[ $kind ] ) ) {
				continue;
			}
			$out[ $slug ] = array(
				'name' => $name,
				'slug' => $slug,
				'kind' => $kind,
				'note' => isset( $tag['note'] ) ? trim( (string) $tag['note'] ) : '',
			);
		}
		return array_values( $out );
	}

	/**
	 * Pure: topics from an index (id => entry, newest first). Each topic: slug, name (the most used spelling), kind (the most
	 * used), the episode ids newest first, first and latest dates, and each episode's own note about it.
	 */
	public static function build_topics( array $index, $show_slug = '' ) {
		$raw = array();
		foreach ( $index as $id => $entry ) {
			if ( '' !== $show_slug && $entry['show'] !== $show_slug ) {
				continue;
			}
			foreach ( $entry['entities'] as $tag ) {
				$slug = $tag['slug'];
				if ( ! isset( $raw[ $slug ] ) ) {
					$raw[ $slug ] = array( 'names' => array(), 'kinds' => array(), 'episodes' => array(), 'notes' => array() );
				}
				$raw[ $slug ]['names'][ $tag['name'] ] = ( $raw[ $slug ]['names'][ $tag['name'] ] ?? 0 ) + 1;
				$raw[ $slug ]['kinds'][ $tag['kind'] ] = ( $raw[ $slug ]['kinds'][ $tag['kind'] ] ?? 0 ) + 1;
				$raw[ $slug ]['episodes'][]            = $id;
				$raw[ $slug ]['notes'][ $id ]          = $tag['note'];
			}
		}
		$topics = array();
		foreach ( $raw as $slug => $data ) {
			arsort( $data['names'] );
			arsort( $data['kinds'] );
			$dates = array();
			foreach ( $data['episodes'] as $id ) {
				$dates[] = $index[ $id ]['date'];
			}
			sort( $dates );
			$topics[ $slug ] = array(
				'slug'     => $slug,
				'name'     => (string) array_key_first( $data['names'] ),
				'kind'     => (string) array_key_first( $data['kinds'] ),
				'count'    => count( $data['episodes'] ),
				'episodes' => $data['episodes'],
				'notes'    => $data['notes'],
				'first'    => $dates[0],
				'latest'   => $dates[ count( $dates ) - 1 ],
			);
		}
		return $topics;
	}

	/**
	 * Pure: up to $limit newscasts related to $id. Score = sum over the tags the two share of (kind weight / ln(1 + the tag's
	 * newscast count)), so a rare, specific shared tag (one company) counts for more than a common one (a broad topic); ties
	 * go to the newer newscast. Newscasts that share nothing only fill the remaining places, newest first, and are flagged
	 * (empty 'shared') so the page can label them as more newscasts rather than as related.
	 */
	public static function pick_related( array $index, array $topics, $id, $limit ) {
		if ( ! isset( $index[ $id ] ) ) {
			return array();
		}
		$kinds = self::kinds();
		$me    = $index[ $id ];
		$scored = array();
		foreach ( $index as $other_id => $other ) {
			if ( $other_id === $id || $other['show'] !== $me['show'] ) {
				continue;
			}
			$shared = array();
			$score  = 0.0;
			$mine   = array();
			foreach ( $me['entities'] as $tag ) {
				$mine[ $tag['slug'] ] = $tag;
			}
			foreach ( $other['entities'] as $tag ) {
				if ( ! isset( $mine[ $tag['slug'] ] ) ) {
					continue;
				}
				$count    = isset( $topics[ $tag['slug'] ] ) ? max( 2, $topics[ $tag['slug'] ]['count'] ) : 2;
				$score   += $kinds[ $tag['kind'] ][2] / log( 1 + $count );
				$shared[] = $mine[ $tag['slug'] ]['name'];
			}
			$scored[] = array( 'id' => $other_id, 'score' => $score, 'shared' => $shared, 'ts' => $other['ts'] );
		}
		usort(
			$scored,
			static function ( $a, $b ) {
				if ( $a['score'] !== $b['score'] ) {
					return $a['score'] < $b['score'] ? 1 : -1;
				}
				return $b['ts'] <=> $a['ts'];
			}
		);
		return array_slice( $scored, 0, max( 0, (int) $limit ) );
	}

	/** Pure: "Frontline Education", "Frontline Education and PowerSchool", "A, B and C". */
	public static function join_names( array $names ) {
		$names = array_values( $names );
		$n     = count( $names );
		if ( $n < 2 ) {
			return $n ? $names[0] : '';
		}
		return implode( ', ', array_slice( $names, 0, $n - 1 ) ) . ' and ' . $names[ $n - 1 ];
	}

	/* ------------------------------------------------------------------ WordPress-backed */

	/** Every published newscast with its tags: id => {id, title, url, date, ts, show, entities[]}, newest first. Cached. */
	public static function index() {
		$cached = get_transient( self::CACHE );
		if ( is_array( $cached ) ) {
			return $cached;
		}
		$index = self::build_index();
		set_transient( self::CACHE, $index, 6 * HOUR_IN_SECONDS );
		return $index;
	}

	private static function build_index() {
		$episodes = get_posts(
			array(
				'post_type'      => 'ng_episode',
				'post_status'    => 'any',
				'posts_per_page' => -1,
				'no_found_rows'  => true,
			)
		);
		$tags_by_podcast = array();
		foreach ( $episodes as $episode ) {
			$podcast_id = (int) get_post_meta( $episode->ID, 'ng_website_post_id', true );
			if ( $podcast_id ) {
				$tags_by_podcast[ $podcast_id ] = self::clean_tags( get_post_meta( $episode->ID, self::META_KEY, true ) );
			}
		}
		if ( ! $tags_by_podcast ) {
			return array();
		}
		$posts = get_posts(
			array(
				'post_type'      => 'podcast',
				'post_status'    => 'publish',
				'post__in'       => array_keys( $tags_by_podcast ),
				'posts_per_page' => -1,
				'orderby'        => 'date',
				'order'          => 'DESC',
				'no_found_rows'  => true,
			)
		);
		$index = array();
		foreach ( $posts as $post ) {
			$terms = get_the_terms( $post->ID, 'series' );
			$show  = ( ! empty( $terms ) && ! is_wp_error( $terms ) ) ? $terms[0]->slug : '';
			if ( '' === $show ) {
				continue;
			}
			$index[ $post->ID ] = array(
				'id'       => $post->ID,
				'title'    => html_entity_decode( get_the_title( $post ), ENT_QUOTES, 'UTF-8' ),
				'url'      => get_permalink( $post ),
				'date'     => get_the_date( 'Y-m-d', $post ),
				'ts'       => (int) get_post_time( 'U', true, $post ),
				'show'     => $show,
				'entities' => $tags_by_podcast[ $post->ID ],
			);
		}
		return $index;
	}

	public static function topics( $show_slug ) {
		return self::build_topics( self::index(), $show_slug );
	}

	/** Topics that have enough newscasts for their own indexable page, biggest first (ties: most recent coverage, then name). */
	public static function page_topics( $show_slug ) {
		$topics = array_filter(
			self::topics( $show_slug ),
			static function ( $t ) {
				return $t['count'] >= self::MIN_TOPIC_EPISODES;
			}
		);
		uasort(
			$topics,
			static function ( $a, $b ) {
				return array( $b['count'], $b['latest'], $a['name'] ) <=> array( $a['count'], $a['latest'], $b['name'] );
			}
		);
		return $topics;
	}

	public static function topic( $show_slug, $slug ) {
		$topics = self::topics( $show_slug );
		return $topics[ $slug ] ?? null;
	}

	public static function topic_url( $show_slug, $slug ) {
		return home_url( '/' . $show_slug . '/topics/' . $slug . '/' );
	}

	public static function topics_index_url( $show_slug ) {
		return home_url( '/' . $show_slug . '/topics/' );
	}

	/** The related newscasts for a public podcast post: array of {entry, shared[]}. */
	public static function related( $podcast_id, $limit = self::RELATED_LIMIT ) {
		$index  = self::index();
		$podcast_id = (int) $podcast_id;
		if ( ! isset( $index[ $podcast_id ] ) ) {
			return array();
		}
		$topics = self::build_topics( $index, $index[ $podcast_id ]['show'] );
		$picked = self::pick_related( $index, $topics, $podcast_id, $limit );
		$out    = array();
		foreach ( $picked as $row ) {
			$shared = $row['shared'];
			if ( $row['score'] <= 0 ) {
				$shared = array();
			}
			$out[] = array( 'entry' => $index[ $row['id'] ], 'shared' => $shared );
		}
		return $out;
	}

	/** The tags of one published newscast. */
	public static function tags_for( $podcast_id ) {
		$index = self::index();
		return isset( $index[ (int) $podcast_id ] ) ? $index[ (int) $podcast_id ]['entities'] : array();
	}
}
