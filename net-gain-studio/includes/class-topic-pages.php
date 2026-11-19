<?php
/**
 * Topic pages (internal linking, 2026-11-19): /{show}/topics/ lists the companies, organizations, places and issues a
 * show has covered, and /{show}/topics/{slug}/ is one page per topic with a dated timeline of every newscast that covered
 * it and what the newscast said (the note the pipeline stored with the tag - our own reporting, not text copied from a
 * source).
 *
 * The pages are virtual: an ordinary WordPress page called "topics" under the show's page (so the theme's header, footer and
 * show colours work unchanged) plus a rewrite rule that adds the topic slug as a query var. The plugin's own template
 * (templates/topics.php) draws them. A topic gets an indexable page only once it has MIN_TOPIC_EPISODES newscasts; with fewer
 * the address still works for anyone who has it but is noindex, and nothing links to it.
 *
 * Search-engine side: title, description, canonical, share tags, schema and sitemap entries are supplied here because AIOSEO
 * only knows the one "topics" page.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Topic_Pages {

	const QUERY_VAR    = 'ng_topic';
	const PAGE_SLUG    = 'topics';
	const REWRITE_FLAG = 'ng_topics_rewrite_v1';

	public static function register() {
		add_action( 'init', array( __CLASS__, 'add_rewrite' ) );
		add_filter( 'query_vars', array( __CLASS__, 'query_vars' ) );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue' ) );
		add_filter( 'redirect_canonical', array( __CLASS__, 'keep_topic_urls' ), 10, 2 );
		add_action( 'template_redirect', array( __CLASS__, 'check_topic' ), 1 );
		add_filter( 'template_include', array( __CLASS__, 'use_template' ), 99 );

		add_filter( 'pre_get_document_title', array( __CLASS__, 'document_title' ), 100000 );
		add_filter( 'aioseo_description', array( __CLASS__, 'description' ), 20 );
		add_filter( 'aioseo_canonical_url', array( __CLASS__, 'canonical' ), 20 );
		add_filter( 'aioseo_facebook_tags', array( __CLASS__, 'social_tags' ), 20 );
		add_filter( 'aioseo_twitter_tags', array( __CLASS__, 'social_tags' ), 20 );
		add_filter( 'aioseo_robots_meta', array( __CLASS__, 'aioseo_robots' ), 99 );
		add_filter( 'wp_robots', array( __CLASS__, 'robots' ), 99 );
		add_filter( 'aioseo_schema_output', array( __CLASS__, 'schema' ), 20 );
		add_filter( 'aioseo_sitemap_posts', array( __CLASS__, 'sitemap_entries' ), 10, 2 );
	}

	/* ------------------------------------------------------------------ routing */

	public static function add_rewrite() {
		add_rewrite_rule( '^([a-z0-9][a-z0-9-]*)/' . self::PAGE_SLUG . '/([a-z0-9][a-z0-9-]*)/?$', 'index.php?pagename=$matches[1]/' . self::PAGE_SLUG . '&' . self::QUERY_VAR . '=$matches[2]', 'top' );
		if ( get_option( self::REWRITE_FLAG ) !== '1' ) {
			flush_rewrite_rules( false );
			update_option( self::REWRITE_FLAG, '1', false );
		}
	}

	public static function query_vars( $vars ) {
		$vars[] = self::QUERY_VAR;
		return $vars;
	}

	/** The page's small script (filter, tabs, sort) - only on the topics pages. */
	public static function enqueue() {
		if ( ! self::is_topics_page() ) {
			return;
		}
		$js = NET_GAIN_PLUGIN_DIR . 'assets/topics.js';
		wp_enqueue_script( 'ng-topics', plugin_dir_url( NET_GAIN_PLUGIN_FILE ) . 'assets/topics.js', array(), NET_GAIN_VERSION . '.' . (int) @filemtime( $js ), true );
	}

	/** WordPress would "correct" /edtech/topics/some-topic/ to the page's own address; the topic address is the right one. */
	public static function keep_topic_urls( $redirect, $requested ) {
		return '' !== self::topic_slug() ? false : $redirect;
	}

	/** The topic slug of this request, or ''. */
	public static function topic_slug() {
		$slug = get_query_var( self::QUERY_VAR );
		return is_string( $slug ) ? $slug : '';
	}

	/** True on the show's "topics" page (the list, or a single topic: both use the same WordPress page). */
	public static function is_topics_page() {
		if ( ! is_page() ) {
			return false;
		}
		$page = get_queried_object();
		if ( ! $page || self::PAGE_SLUG !== $page->post_name || ! $page->post_parent ) {
			return false;
		}
		return null !== self::show_slug();
	}

	/** The show this topics page belongs to (its parent page's slug, when that is a show), or null. */
	public static function show_slug() {
		$page = get_queried_object();
		if ( ! $page || ! isset( $page->post_parent ) || ! $page->post_parent ) {
			return null;
		}
		$slug = get_post_field( 'post_name', $page->post_parent );
		return ( $slug && get_term_by( 'slug', $slug, 'series' ) ) ? $slug : null;
	}

	/** The topic being shown: array, or null when this is the list page or the slug is unknown. */
	public static function current_topic() {
		$slug = self::topic_slug();
		$show = self::show_slug();
		if ( '' === $slug || null === $show ) {
			return null;
		}
		return Net_Gain_Entities::topic( $show, $slug );
	}

	public static function check_topic() {
		if ( ! self::is_topics_page() || '' === self::topic_slug() ) {
			return;
		}
		if ( null === self::current_topic() ) {
			global $wp_query;
			$wp_query->set_404();
			status_header( 404 );
			nocache_headers();
			return;
		}
		if ( self::is_thin( self::current_topic() ) ) {
			header( 'X-Robots-Tag: noindex, follow' );
		}
	}

	public static function use_template( $template ) {
		if ( self::is_topics_page() ) {
			$own = NET_GAIN_PLUGIN_DIR . 'templates/topics.php';
			if ( is_readable( $own ) ) {
				return $own;
			}
		}
		return $template;
	}

	public static function is_thin( $topic ) {
		return $topic['count'] < Net_Gain_Entities::MIN_TOPIC_EPISODES;
	}

	/* ------------------------------------------------------------------ wording (pure: unit-tested) */

	/** Pure: the first variant whose length is inside [min, max]; otherwise the one closest to the window. */
	public static function pick_fit( array $variants, $min, $max ) {
		$best = null;
		$gap  = PHP_INT_MAX;
		foreach ( $variants as $text ) {
			$len = mb_strlen( $text );
			if ( $len >= $min && $len <= $max ) {
				return $text;
			}
			$distance = $len < $min ? $min - $len : $len - $max;
			if ( $distance < $gap ) {
				$gap  = $distance;
				$best = $text;
			}
		}
		return (string) $best;
	}

	/** Pure: the name as search-result text: ordinary hyphens (the house non-breaking hyphen is for on-page text only). */
	private static function plain( $name ) {
		return str_replace( "\xE2\x80\x91", '-', (string) $name );
	}

	/** Pure: search-result title (ordinary hyphens, as AIOSEO titles use; window about 44 to 62 characters, no site suffix). */
	public static function topic_title( $name ) {
		$name = self::plain( $name );
		$k    = false === stripos( $name, 'K-12' ) ? 'K-12 ' : '';   // do not say K-12 twice
		return self::pick_fit(
			array(
				"$name: {$k}education technology news and newscasts",
				"$name in {$k}edtech news: every newscast on it",
				"$name: {$k}edtech news and newscasts",
				"$name news for {$k}district leaders: newscast archive",
				"$name: {$k}edtech news",
				"$name: {$k}edtech newscasts",
			),
			44,
			62
		);
	}

	/** Pure: meta description, 121 to 160 characters. $first is a 'Y-m-d' date. */
	public static function topic_description( $name, $count, $first, $show_name ) {
		$name  = self::plain( $name );
		$since = mysql2date( 'F j, Y', $first );
		$k     = false === stripos( $name, 'K-12' ) ? 'K-12 ' : '';
		$n     = (int) $count;
		$casts = 1 === $n ? "$n newscast" : "$n newscasts";
		return self::pick_fit(
			array(
				"$name in {$k}edtech news: $casts from $show_name since $since, each with what we reported and links to the full episode.",
				"$name in {$k}edtech news: $casts from $show_name since $since, with what we reported each time and the episode links.",
				"$name in {$k}edtech news: $casts since $since, with what we reported each time and links to every episode.",
				"$name: $casts from $show_name since $since on {$k}education technology, security and policy, with the full episode for each.",
			),
			121,
			160
		);
	}

	public static function index_title( $show_name ) {
		return self::pick_fit(
			array(
				"$show_name topics: companies, places and issues in K-12 news",
				"$show_name topics: the companies and issues we cover",
				"Topics in K-12 edtech news: companies, places and issues",
			),
			44,
			62
		);
	}

	public static function index_description( $show_name, $topic_count, $newscast_count ) {
		return self::pick_fit(
			array(
				"Browse $topic_count companies, organizations, places and issues covered in $newscast_count $show_name newscasts on K-12 education technology, security and policy.",
				"Browse the companies, organizations, places and issues covered in $newscast_count $show_name newscasts on K-12 education technology, security and policy.",
				"Browse the companies, places and issues covered in $newscast_count $show_name newscasts on K-12 technology, security and policy.",
			),
			121,
			160
		);
	}

	/* ------------------------------------------------------------------ search-engine output */

	private static function show_name() {
		$show = self::show_slug();
		$term = $show ? get_term_by( 'slug', $show, 'series' ) : null;
		return $term ? $term->name : get_bloginfo( 'name' );
	}

	/** Title/description/canonical for the current request: array or null when this is not one of our pages. */
	private static function seo() {
		static $cache = array();
		if ( ! self::is_topics_page() ) {
			return null;
		}
		$key = self::topic_slug();
		if ( isset( $cache[ $key ] ) ) {
			return $cache[ $key ];
		}
		$show      = self::show_slug();
		$show_name = self::show_name();
		$topic     = self::current_topic();
		if ( '' !== $key && null === $topic ) {
			return null;
		}
		if ( $topic ) {
			$seo = array(
				'title'       => self::topic_title( $topic['name'] ),
				'description' => self::topic_description( $topic['name'], $topic['count'], $topic['first'], $show_name ),
				'canonical'   => Net_Gain_Entities::topic_url( $show, $topic['slug'] ),
				'thin'        => self::is_thin( $topic ),
			);
		} else {
			$seo = array(
				'title'       => self::index_title( $show_name ),
				'description' => self::index_description( $show_name, count( Net_Gain_Entities::page_topics( $show ) ), count( array_filter( Net_Gain_Entities::index(), static function ( $e ) use ( $show ) { return $e['show'] === $show; } ) ) ),
				'canonical'   => Net_Gain_Entities::topics_index_url( $show ),
				'thin'        => false,
			);
		}
		$cache[ $key ] = $seo;
		return $seo;
	}

	public static function document_title( $title ) {
		$seo = self::seo();
		return $seo ? $seo['title'] : $title;
	}

	public static function description( $description ) {
		$seo = self::seo();
		return $seo ? $seo['description'] : $description;
	}

	public static function canonical( $url ) {
		$seo = self::seo();
		return $seo ? $seo['canonical'] : $url;
	}

	public static function social_tags( $meta ) {
		$seo = self::seo();
		if ( ! $seo ) {
			return $meta;
		}
		foreach ( array( 'og:title', 'twitter:title' ) as $key ) {
			if ( isset( $meta[ $key ] ) ) {
				$meta[ $key ] = $seo['title'];
			}
		}
		foreach ( array( 'og:description', 'twitter:description' ) as $key ) {
			if ( isset( $meta[ $key ] ) ) {
				$meta[ $key ] = $seo['description'];
			}
		}
		if ( isset( $meta['og:url'] ) ) {
			$meta['og:url'] = $seo['canonical'];
		}
		return $meta;
	}

	public static function aioseo_robots( $attributes ) {
		$seo = self::seo();
		if ( $seo && $seo['thin'] ) {
			$attributes['noindex'] = 'noindex';
			unset( $attributes['index'] );
		}
		return $attributes;
	}

	public static function robots( $robots ) {
		$seo = self::seo();
		if ( $seo && $seo['thin'] ) {
			$robots['noindex'] = true;
			unset( $robots['index'] );
		}
		return $robots;
	}

	/** Makes the WebPage node describe this topic and gives the breadcrumb its extra step; adds the list of newscasts. */
	public static function schema( $graph ) {
		$seo = self::seo();
		if ( ! $seo || ! is_array( $graph ) ) {
			return $graph;
		}
		$topic = self::current_topic();
		$show  = self::show_slug();
		foreach ( $graph as $i => $node ) {
			if ( ! isset( $node['@type'] ) ) {
				continue;
			}
			if ( 'WebPage' === $node['@type'] ) {
				$graph[ $i ]['@type']       = 'CollectionPage';
				$graph[ $i ]['url']         = $seo['canonical'];
				$graph[ $i ]['name']        = $seo['title'];
				$graph[ $i ]['description'] = $seo['description'];
				$graph[ $i ]['@id']         = $seo['canonical'] . '#webpage';
			}
			if ( 'BreadcrumbList' === $node['@type'] && $topic && isset( $node['itemListElement'] ) && is_array( $node['itemListElement'] ) ) {
				$items = $node['itemListElement'];
				$last  = count( $items );
				$items[] = array(
					'@type'    => 'ListItem',
					'@id'      => $seo['canonical'] . '#listItem',
					'position' => $last + 1,
					'name'     => $topic['name'],
					'item'     => $seo['canonical'],
				);
				$graph[ $i ]['itemListElement'] = $items;
			}
		}
		if ( $topic ) {
			$index = Net_Gain_Entities::index();
			$list  = array();
			foreach ( $topic['episodes'] as $position => $id ) {
				if ( isset( $index[ $id ] ) ) {
					$list[] = array(
						'@type'    => 'ListItem',
						'position' => $position + 1,
						'url'      => $index[ $id ]['url'],
						'name'     => $index[ $id ]['title'],
					);
				}
			}
			$graph[] = array(
				'@type'           => 'ItemList',
				'@id'             => $seo['canonical'] . '#itemlist',
				'name'            => $topic['name'] . ' newscasts',
				'itemListOrder'   => 'https://schema.org/ItemListOrderDescending',
				'numberOfItems'   => count( $list ),
				'itemListElement' => $list,
			);
		}
		unset( $show );
		return $graph;
	}

	/** The page sitemap gets the index page's neighbours: every topic that has an indexable page of its own. */
	public static function sitemap_entries( $entries, $post_type = '' ) {
		if ( 'page' !== $post_type || ! is_array( $entries ) ) {
			return $entries;
		}
		foreach ( get_terms( array( 'taxonomy' => 'series', 'hide_empty' => true, 'fields' => 'slugs' ) ) as $show ) {
			foreach ( Net_Gain_Entities::page_topics( $show ) as $topic ) {
				$entries[] = array(
					'loc'        => Net_Gain_Entities::topic_url( $show, $topic['slug'] ),
					'lastmod'    => gmdate( 'c', strtotime( $topic['latest'] . ' 12:00:00 UTC' ) ),
					'changefreq' => 'weekly',
					'priority'   => 0.6,
				);
			}
		}
		return $entries;
	}
}
